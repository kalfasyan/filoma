use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use std::time::Instant;

use futures::future::BoxFuture;
use pyo3::prelude::*;
use tokio::fs;
use tokio::sync::Semaphore;
use tokio::time::{timeout, sleep, Duration};

use crate::{analysis::get_file_extension, AnalysisConfig, ParallelDirectoryStats};

// Async scanning implementation tuned for higher-latency filesystems (NFS/CIFS)

// Backoff constants for retry logic
const READDIR_BACKOFF_BASE_MS: u64 = 50;
const METADATA_BACKOFF_BASE_MS: u64 = 10;

/// Tracks I/O errors and timeouts during async scanning (for diagnostics)
#[derive(Debug, Default)]
struct ScanMetrics {
    readdir_timeouts: AtomicU64,
    readdir_errors: AtomicU64,
    metadata_timeouts: AtomicU64,
    metadata_errors: AtomicU64,
    skipped_entries: AtomicU64,
}

impl ScanMetrics {
    fn new() -> Self {
        Self::default()
    }

    fn record_readdir_timeout(&self) {
        self.readdir_timeouts.fetch_add(1, Ordering::Relaxed);
    }

    fn record_readdir_error(&self) {
        self.readdir_errors.fetch_add(1, Ordering::Relaxed);
    }

    fn record_metadata_timeout(&self) {
        self.metadata_timeouts.fetch_add(1, Ordering::Relaxed);
    }

    fn record_metadata_error(&self) {
        self.metadata_errors.fetch_add(1, Ordering::Relaxed);
    }

    fn record_skipped_entry(&self) {
        self.skipped_entries.fetch_add(1, Ordering::Relaxed);
    }

    /// Returns true if any errors/timeouts were recorded
    fn has_issues(&self) -> bool {
        self.readdir_timeouts.load(Ordering::Relaxed) > 0
            || self.readdir_errors.load(Ordering::Relaxed) > 0
            || self.metadata_timeouts.load(Ordering::Relaxed) > 0
            || self.metadata_errors.load(Ordering::Relaxed) > 0
    }

    /// Log a summary if there were any issues (useful for debugging)
    #[allow(dead_code)]
    fn summary(&self) -> String {
        format!(
            "ScanMetrics {{ readdir_timeouts: {}, readdir_errors: {}, metadata_timeouts: {}, metadata_errors: {}, skipped: {} }}",
            self.readdir_timeouts.load(Ordering::Relaxed),
            self.readdir_errors.load(Ordering::Relaxed),
            self.metadata_timeouts.load(Ordering::Relaxed),
            self.metadata_errors.load(Ordering::Relaxed),
            self.skipped_entries.load(Ordering::Relaxed),
        )
    }
}

pub async fn probe_directory_async_internal(
    path_root: PathBuf,
    config: AnalysisConfig,
    concurrency_limit: usize,
    timeout_ms: u64,
    retries: u8,
) -> Result<crate::DirectoryStats, String> {
    let start = Instant::now();

    // Use the ParallelDirectoryStats structure for thread-safe aggregation
    let stats = Arc::new(ParallelDirectoryStats::new());
    let sem = Arc::new(Semaphore::new(concurrency_limit));
    let metrics = Arc::new(ScanMetrics::new());

    // Count the root directory only if it is non-empty. If the root is empty, the
    // recursive scanner will record it via the `is_empty` branch; adding it here
    // unconditionally would double-count the root for empty directories.
    if let Some(name) = path_root.file_name().and_then(|n| n.to_str()) {
        let is_empty = crate::analysis::estimate_directory_size(&path_root, 1) == 0;
        if !is_empty {
            stats.add_folder(name.to_string(), false, path_root.to_string_lossy().to_string(), 0);
        }
    }

    // Kick off scanning from root
    let root_clone = path_root.clone();
    let stats_clone = stats.clone();
    let config_clone = config.clone();
    let metrics_clone = metrics.clone();

    let res = scan_dir_recursive(root_clone, stats_clone, config_clone, sem.clone(), 0u32, timeout_ms, retries, metrics_clone).await;
    if let Err(e) = res {
        return Err(e);
    }

    // Convert to DirectoryStats and set timing
    let mut result = stats.to_directory_stats();
    let elapsed = start.elapsed();
    result.set_timing(elapsed.as_secs_f64());

    // Log metrics summary if there were issues (could be exposed to Python in future)
    if metrics.has_issues() {
        // For now, metrics are tracked but not exposed. Could add to result dict later.
        #[cfg(debug_assertions)]
        eprintln!("[filoma async] {}", metrics.summary());
    }

    Ok(result)
}

fn scan_dir_recursive(
    dir: PathBuf,
    stats: Arc<ParallelDirectoryStats>,
    config: AnalysisConfig,
    sem: Arc<Semaphore>,
    current_depth: u32,
    timeout_ms: u64,
    retries: u8,
    metrics: Arc<ScanMetrics>,
) -> BoxFuture<'static, Result<(), String>> {
    Box::pin(async move {
        // Respect max_depth
        if let Some(max_d) = config.max_depth {
            if current_depth > max_d {
                return Ok(());
            }
        }

        // Acquire a permit to limit concurrency
        let permit = sem.acquire().await.map_err(|e| format!("Semaphore closed: {}", e))?;

        // Read directory entries with timeout & retries
        let mut attempt = 0u8;
        let read_dir = loop {
            let fut = fs::read_dir(&dir);
            match timeout(Duration::from_millis(timeout_ms), fut).await {
                Ok(Ok(rd)) => break rd,
                Ok(Err(_e)) => {
                    metrics.record_readdir_error();
                }
                Err(_) => {
                    metrics.record_readdir_timeout();
                }
            }

            if attempt >= retries {
                // Release permit and skip this directory
                metrics.record_skipped_entry();
                drop(permit);
                return Ok(());
            }
            attempt += 1;
            // Exponential backoff with configurable base
            sleep(Duration::from_millis(READDIR_BACKOFF_BASE_MS * (1 << attempt.min(4)))).await;
        };

        // Process entries - release permit early once we have the directory listing
        // This allows other tasks to proceed while we process entries
        drop(permit);

        let mut entries = read_dir;
        let mut is_empty = true;

        while let Ok(Some(entry)) = entries.next_entry().await {
            is_empty = false;
            let path = entry.path();
            
            // Metadata with timeout & retries
            let mut meta_attempt = 0u8;
            let metadata = loop {
                match timeout(Duration::from_millis(timeout_ms), entry.metadata()).await {
                    Ok(Ok(md)) => break Some(md),
                    Ok(Err(_e)) => {
                        metrics.record_metadata_error();
                    }
                    Err(_) => {
                        metrics.record_metadata_timeout();
                    }
                }

                if meta_attempt >= retries {
                    break None;
                }
                meta_attempt += 1;
                // Exponential backoff with configurable base
                sleep(Duration::from_millis(METADATA_BACKOFF_BASE_MS * (1 << meta_attempt.min(4)))).await;
            };

            if let Some(md) = metadata {
                if md.is_dir() {
                    // Add folder
                    // Use adjusted depth semantics to match the sequential prober
                    // (sequential uses adjusted_depth = if depth == 0 { 0 } else { depth - 1 })
                    // Here, current_depth represents the adjusted depth of `dir`, so child folders
                    // should be recorded with the same adjusted depth value before recursing.
                    if let Some(name) = path.file_name().and_then(|n| n.to_str()) {
                        stats.add_folder(
                            name.to_string(),
                            false,
                            path.to_string_lossy().to_string(),
                            current_depth,
                        );
                    }

                    // Recurse into subdirectory (await serially within this async call)
                    // Note: This is intentionally sequential to maintain bounded memory usage
                    // and simpler error handling for network filesystems.
                    let _ = scan_dir_recursive(
                        path.clone(),
                        stats.clone(),
                        config.clone(),
                        sem.clone(),
                        current_depth + 1,
                        timeout_ms,
                        retries,
                        metrics.clone(),
                    ).await;
                } else if md.is_file() {
                    // Handle file
                    let ext = get_file_extension(&path);
                    let size = if config.fast_path_only { 0 } else { md.len() };
                    let parent = path.parent().map(|p| p.to_string_lossy().to_string()).unwrap_or_default();
                    stats.add_file(size, ext, parent, config.fast_path_only);
                }
            } else {
                // Metadata failed after retries; skip this entry
                metrics.record_skipped_entry();
                continue;
            }
        }

        // If directory turned out to be empty, record it
        if is_empty {
            if let Some(name) = dir.file_name().and_then(|n| n.to_str()) {
                stats.add_folder(name.to_string(), true, dir.to_string_lossy().to_string(), current_depth);
            }
        }

        Ok(())
    })
}

#[pyfunction]
#[pyo3(signature = (path_root, max_depth=None, concurrency_limit=None, timeout_ms=None, retries=None, fast_path_only=None, follow_links=None, search_hidden=None, no_ignore=None))]
pub(crate) fn probe_directory_rust_async(path_root: &str, max_depth: Option<u32>, concurrency_limit: Option<usize>, timeout_ms: Option<u64>, retries: Option<u8>, fast_path_only: Option<bool>, follow_links: Option<bool>, search_hidden: Option<bool>, no_ignore: Option<bool>) -> PyResult<PyObject> {
    let root = PathBuf::from(path_root);

    if !root.exists() {
        return Err(pyo3::exceptions::PyValueError::new_err(format!("Path does not exist: {}", path_root)));
    }
    if !root.is_dir() {
        return Err(pyo3::exceptions::PyValueError::new_err(format!("Path is not a directory: {}", path_root)));
    }

    // Build config
    let config = AnalysisConfig {
        max_depth,
        follow_links: follow_links.unwrap_or(true),
        search_hidden: search_hidden.unwrap_or(true),
        no_ignore: no_ignore.unwrap_or(true),
        parallel: true,
        parallel_threshold: 1000,
        log_progress: false,
        fast_path_only: fast_path_only.unwrap_or(false),
    };

    let concurrency = concurrency_limit.unwrap_or(64);
    let op_timeout_ms = timeout_ms.unwrap_or(5000);
    let retries = retries.unwrap_or(0);

    // Build a runtime and block_on the async analysis
    let rt = tokio::runtime::Builder::new_multi_thread()
        .enable_all()
        .build()
        .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(format!("Failed to build tokio runtime: {}", e)))?;

    // Wrap the internal call to inject timeout/retry behavior into a config closure
    let stats = rt.block_on(async move {
        probe_directory_async_internal(root, config, concurrency, op_timeout_ms, retries).await
    });

    let stats = stats.map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e))?;

    Python::with_gil(|py| stats.to_py_dict(py, path_root))
}
