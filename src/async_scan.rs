use std::path::PathBuf;
use std::sync::Arc;
use std::time::Instant;

use futures::future::BoxFuture;
use pyo3::prelude::*;
use tokio::fs;
use tokio::sync::Semaphore;
use tokio::time::{timeout, sleep, Duration};

use crate::{analysis::get_file_extension, AnalysisConfig, ParallelDirectoryStats};

// Async scanning implementation tuned for higher-latency filesystems (NFS/CIFS)

pub async fn analyze_directory_async_internal(
    root_path: PathBuf,
    config: AnalysisConfig,
    concurrency_limit: usize,
    timeout_ms: u64,
    retries: u8,
) -> Result<crate::DirectoryStats, String> {
    let start = Instant::now();

    // Use the ParallelDirectoryStats structure for thread-safe aggregation
    let stats = Arc::new(ParallelDirectoryStats::new());
    let sem = Arc::new(Semaphore::new(concurrency_limit));

    // Count the root directory only if it is non-empty. If the root is empty, the
    // recursive scanner will record it via the `is_empty` branch; adding it here
    // unconditionally would double-count the root for empty directories.
    if let Some(name) = root_path.file_name().and_then(|n| n.to_str()) {
        let is_empty = crate::analysis::estimate_directory_size(&root_path, 1) == 0;
        if !is_empty {
            stats.add_folder(name.to_string(), false, root_path.to_string_lossy().to_string(), 0);
        }
    }

    // Kick off scanning from root
    let root_clone = root_path.clone();
    let stats_clone = stats.clone();
    let config_clone = config.clone();

    let res = scan_dir_recursive(root_clone, stats_clone, config_clone, sem.clone(), 0u32, timeout_ms, retries).await;
    if let Err(e) = res {
        return Err(e);
    }

    // Convert to DirectoryStats and set timing
    let mut result = stats.to_directory_stats();
    let elapsed = start.elapsed();
    result.set_timing(elapsed.as_secs_f64());

    // No ad-hoc adjustments here; `stats` already records folders including the root.

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
                Ok(Err(_)) => {
                    // io error
                }
                Err(_) => {
                    // timeout
                }
            }

            if attempt >= retries {
                // release permit and skip this directory
                drop(permit);
                return Ok(());
            }
            attempt += 1;
            // simple backoff
            sleep(Duration::from_millis(50 * attempt as u64)).await;
        };

        // Estimate emptiness by sampling first entry
        let mut entries = read_dir;
        let mut is_empty = true;

        while let Ok(Some(entry)) = entries.next_entry().await {
            is_empty = false;
            let path = entry.path();
            // metadata with timeout & retries
            let mut meta_attempt = 0u8;
            let metadata = loop {
                match timeout(Duration::from_millis(timeout_ms), entry.metadata()).await {
                    Ok(Ok(md)) => break Some(md),
                    Ok(Err(_)) => {
                        // io error
                    }
                    Err(_) => {
                        // timeout
                    }
                }

                if meta_attempt >= retries {
                    break None;
                }
                meta_attempt += 1;
                sleep(Duration::from_millis(10 * meta_attempt as u64)).await;
            };

            if let Some(md) = metadata {
                if md.is_dir() {
                    // Add folder
                    // Use adjusted depth semantics to match the sequential analyzer
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
                    let _ = scan_dir_recursive(path.clone(), stats.clone(), config.clone(), sem.clone(), current_depth + 1, timeout_ms, retries).await;
                } else if md.is_file() {
                    // Handle file
                    let ext = get_file_extension(&path);
                    let size = if config.fast_path_only { 0 } else { md.len() };
                    let parent = path.parent().map(|p| p.to_string_lossy().to_string()).unwrap_or_default();
                    stats.add_file(size, ext, parent, config.fast_path_only);
                }
            } else {
                // Metadata failed after retries; skip
                continue;
            }
        }

        // If directory turned out to be empty, record it
        if is_empty {
            if let Some(name) = dir.file_name().and_then(|n| n.to_str()) {
                stats.add_folder(name.to_string(), true, dir.to_string_lossy().to_string(), current_depth);
            }
        }

        // Release permit
        drop(permit);
        Ok(())
    })
}

#[pyfunction]
pub(crate) fn analyze_directory_rust_async(root_path: &str, max_depth: Option<u32>, concurrency_limit: Option<usize>, timeout_ms: Option<u64>, retries: Option<u8>, fast_path_only: Option<bool>) -> PyResult<PyObject> {
    let root = PathBuf::from(root_path);

    if !root.exists() {
        return Err(pyo3::exceptions::PyValueError::new_err(format!("Path does not exist: {}", root_path)));
    }
    if !root.is_dir() {
        return Err(pyo3::exceptions::PyValueError::new_err(format!("Path is not a directory: {}", root_path)));
    }

    // Build config
    let config = AnalysisConfig {
        max_depth,
        follow_links: false,
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
        analyze_directory_async_internal(root, config, concurrency, op_timeout_ms, retries).await
    });

    let stats = stats.map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e))?;

    Python::with_gil(|py| stats.to_py_dict(py, root_path))
}
