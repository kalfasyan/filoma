//! Parallel directory analysis engine built on `dua-core`.
//!
//! `dua-core` parallelizes both `read_dir` and (on Unix) metadata retrieval
//! across a work-stealing worker pool, and consumes metadata from directory
//! enumeration directly on Windows (NTFS). Unlike the walkdir-based engines,
//! no extra `read_dir` syscall is needed per directory for empty-folder
//! detection: emptiness is derived from which directories received children.
//!
//! Semantics deliberately mirror the walkdir-based parallel engine
//! (`crate::parallel::probe_directory_parallel`):
//! - depth of the root is 0; files at depth `max_depth + 1` are included
//! - hidden entries are skipped when `search_hidden` is false
//! - errors are skipped (counted as nothing)
//! - symlinks are never followed (matching `follow_links=false`)

use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::Instant;

use dashmap::DashSet;
use dua_core::{walk, Entry, Order};
use pyo3::prelude::*;

use crate::{
    analysis::get_file_extension, make_absolute_path_str, AnalysisConfig, DirectoryStats,
    ParallelDirectoryStats,
};

/// Parallel directory analysis using `dua-core`'s work-stealing walker.
///
/// When `collect_paths` is true, the paths of every counted entry (files and
/// directories) are returned alongside the stats, so callers can build a
/// DataFrame without a second traversal.
pub fn probe_directory_dua_core_internal(
    path_root: &Path,
    config: &AnalysisConfig,
    threads: usize,
    collect_paths: bool,
) -> Result<(DirectoryStats, Vec<String>), String> {
    let start_time = Instant::now();
    let stats = Arc::new(ParallelDirectoryStats::new());
    let root_abs = path_root
        .canonicalize()
        .unwrap_or_else(|_| path_root.to_path_buf());

    // Absolute paths of every directory that was counted (empty-dir detection).
    let all_dirs: DashSet<String> = DashSet::new();
    // Absolute paths of every directory that received at least one child.
    let parents_with_children: DashSet<String> = DashSet::new();
    // Paths of every counted entry, collected on the consuming thread.
    let mut paths: Vec<String> = Vec::new();

    // Count the root directory itself, mirroring `probe_root_directory`:
    // only when it has a file name (a bare "." probe has none), and its
    // emptiness is resolved below from the children we observe.
    if let Some(name) = path_root.file_name().and_then(|n| n.to_str()) {
        stats.add_folder(
            name.to_string(),
            false,
            path_root.to_string_lossy().to_string(),
            0,
        );
        // The root is counted in the stats but excluded from the returned
        // paths, matching the rglob-based DataFrame collection (rglob("*")
        // never yields the root itself).
        all_dirs.insert(make_absolute_path_str(
            path_root, path_root, &root_abs, false,
        ));
    }

    // Files at depth `max_depth + 1` are included, so descend into
    // directories up to depth `max_depth` (exclusive upper bound).
    let max_depth = config.max_depth.map(|d| d as usize);
    let descend = move |entry: &Entry| -> bool {
        match max_depth {
            Some(limit) => entry.depth < limit + 1,
            None => true,
        }
    };

    for result in walk(path_root, threads.max(1), Order::ParentFirst, descend) {
        let entry = match result {
            Ok(entry) => entry,
            Err(_) => continue, // Skip inaccessible entries
        };

        // The root entry is already counted above.
        if entry.depth == 0 {
            continue;
        }

        let path = entry.path();
        let parent_abs = make_absolute_path_str(&entry.parent_path, path_root, &root_abs, false);

        // Record the parent as having children before any visibility filtering,
        // so empty-folder detection is not affected by skipped hidden entries
        // (a directory containing only hidden entries is not empty).
        parents_with_children.insert(parent_abs.clone());

        // Skip hidden entries unless search_hidden is enabled.
        if !config.search_hidden {
            if let Some(name) = entry.file_name.to_str() {
                if name.starts_with('.') {
                    continue;
                }
            }
        }

        // Classify using the parallelized metadata when available, falling
        // back to the readdir file type (which may be unknown on filesystems
        // without d_type, e.g. some network mounts). Entries that are neither
        // file nor directory (symlinks, special files) are not counted,
        // mirroring the walkdir engines (is_dir/is_file both false -> skipped).
        let (is_dir, size) = match entry.metadata.as_ref() {
            Ok(metadata) => {
                let file_type = metadata.file_type();
                if file_type.is_dir() {
                    (true, metadata.len())
                } else if file_type.is_file() {
                    (false, metadata.len())
                } else {
                    continue;
                }
            }
            Err(_) => {
                let file_type = entry.file_type;
                if file_type.is_dir() {
                    (true, 0)
                } else if file_type.is_file() {
                    (false, 0)
                } else {
                    continue;
                }
            }
        };

        if is_dir {
            // Mirror the canonical max_depth semantics (Python backend and the
            // sequential walkdir engine): directories at depth > max_depth are
            // not counted, even though dua-core yields them (rejected by the
            // descend predicate but still reported).
            if let Some(limit) = config.max_depth {
                if entry.depth as u32 > limit {
                    continue;
                }
            }
            let dir_abs = make_absolute_path_str(&path, path_root, &root_abs, false);
            if let Some(name) = entry.file_name.to_str() {
                stats.add_folder(name.to_string(), false, dir_abs.clone(), entry.depth as u32);
                all_dirs.insert(dir_abs.clone());
                if collect_paths {
                    paths.push(dir_abs);
                }
            }
        } else {
            let ext = get_file_extension(&path);
            let file_size = if config.fast_path_only { 0 } else { size };
            stats.add_file(file_size, ext, parent_abs, config.fast_path_only);
            if collect_paths {
                paths.push(make_absolute_path_str(&path, path_root, &root_abs, false));
            }
        }
    }

    // Any directory that was counted but never received a child is empty.
    let empty_folders: Vec<String> = all_dirs
        .iter()
        .filter(|dir| !parents_with_children.contains(dir.key()))
        .map(|dir| dir.key().clone())
        .collect();
    stats.add_empty_folders(empty_folders);

    let elapsed = start_time.elapsed();
    let mut result = stats.to_directory_stats();
    result.set_timing(elapsed.as_secs_f64());

    Ok((result, paths))
}

/// Python entry point for the dua-core walker.
#[pyfunction]
#[pyo3(signature = (path_root, max_depth=None, fast_path_only=None, search_hidden=None, walker_threads=None, return_paths=None))]
pub(crate) fn probe_directory_rust_dua_core(
    path_root: &str,
    max_depth: Option<u32>,
    fast_path_only: Option<bool>,
    search_hidden: Option<bool>,
    walker_threads: Option<usize>,
    return_paths: Option<bool>,
) -> PyResult<PyObject> {
    let root = PathBuf::from(path_root);

    if !root.exists() {
        return Err(pyo3::exceptions::PyValueError::new_err(format!(
            "Path does not exist: {}",
            path_root
        )));
    }
    if !root.is_dir() {
        return Err(pyo3::exceptions::PyValueError::new_err(format!(
            "Path is not a directory: {}",
            path_root
        )));
    }

    // dua-core never follows symlinks; this engine is only valid for the
    // follow_links=false semantics.
    let config = AnalysisConfig {
        max_depth,
        follow_links: false,
        search_hidden: search_hidden.unwrap_or(true),
        no_ignore: true,
        parallel: true,
        parallel_threshold: 0,
        log_progress: false,
        fast_path_only: fast_path_only.unwrap_or(false),
    };

    let threads = walker_threads
        .unwrap_or_else(|| {
            std::thread::available_parallelism()
                .map(|n| n.get())
                .unwrap_or(4)
                .max(4)
        })
        .clamp(1, 512);

    let collect_paths = return_paths.unwrap_or(false);

    Python::with_gil(|py| {
        // Release the GIL while walking (dua-core has no per-operation
        // timeouts; a slow mount must not block other Python threads) and
        // convert Rust panics into a typed error so the Python-side fallback
        // can catch them (PanicException does not subclass Exception).
        let (stats, paths) = py
            .allow_threads(|| {
                std::panic::catch_unwind(|| {
                    probe_directory_dua_core_internal(&root, &config, threads, collect_paths)
                })
                .map_err(|_| "dua-core walker panicked".to_string())
                .and_then(|result| result)
            })
            .map_err(pyo3::exceptions::PyRuntimeError::new_err)?;
        let dict = stats.to_py_dict(py, path_root)?;
        if collect_paths {
            dict.downcast_bound::<pyo3::types::PyDict>(py)?
                .set_item("paths", paths)?;
        }
        Ok(dict)
    })
}
