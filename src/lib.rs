use pyo3::prelude::*;
use pyo3::types::{PyDict, PyModule};
use pyo3::Bound;
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU32, AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use walkdir::{DirEntry, WalkDir};
use rayon::prelude::*;
use dashmap::DashMap;

/// Configuration for directory analysis
#[derive(Debug, Clone)]
pub struct AnalysisConfig {
    pub max_depth: Option<u32>,
    pub follow_links: bool,
    pub parallel: bool,
    pub parallel_threshold: usize,
}

impl Default for AnalysisConfig {
    fn default() -> Self {
        Self {
            max_depth: None,
            follow_links: false,
            parallel: true,
            parallel_threshold: 1000, // Use parallel processing for directories with >1000 entries
        }
    }
}

/// Thread-safe statistics collector for parallel processing
#[derive(Debug)]
pub struct ParallelDirectoryStats {
    total_files: AtomicU64,
    total_folders: AtomicU64,
    total_size: AtomicU64,
    max_depth: AtomicU32,
    empty_folders: Arc<Mutex<Vec<String>>>,
    file_extensions: DashMap<String, u64>,
    folder_names: DashMap<String, u64>,
    files_per_folder: DashMap<String, u64>,
    depth_distribution: DashMap<u32, u64>,
}

impl ParallelDirectoryStats {
    fn new() -> Self {
        Self {
            total_files: AtomicU64::new(0),
            total_folders: AtomicU64::new(0),
            total_size: AtomicU64::new(0),
            max_depth: AtomicU32::new(0),
            empty_folders: Arc::new(Mutex::new(Vec::new())),
            file_extensions: DashMap::new(),
            folder_names: DashMap::new(),
            files_per_folder: DashMap::new(),
            depth_distribution: DashMap::new(),
        }
    }

    fn add_file(&self, size: u64, extension: String, parent_path: String) {
        self.total_files.fetch_add(1, Ordering::Relaxed);
        self.total_size.fetch_add(size, Ordering::Relaxed);
        
        // Update extension count
        *self.file_extensions.entry(extension).or_insert(0) += 1;
        
        // Update files per folder count
        *self.files_per_folder.entry(parent_path).or_insert(0) += 1;
    }

    fn add_folder(&self, name: String, is_empty: bool, path: String, depth: u32) {
        self.total_folders.fetch_add(1, Ordering::Relaxed);
        
        // Update max depth atomically
        self.max_depth.fetch_max(depth, Ordering::Relaxed);
        
        // Update folder name count
        *self.folder_names.entry(name).or_insert(0) += 1;
        
        // Initialize files count for this folder
        self.files_per_folder.entry(path.clone()).or_insert(0);
        
        // Add to empty folders if needed
        if is_empty {
            if let Ok(mut empty_folders) = self.empty_folders.lock() {
                empty_folders.push(path);
            }
        }

        // Update depth distribution
        *self.depth_distribution.entry(depth).or_insert(0) += 1;
    }

    fn to_directory_stats(&self) -> DirectoryStats {
        let empty_folders = self.empty_folders.lock()
            .map(|v| v.clone())
            .unwrap_or_default();

        DirectoryStats {
            total_files: self.total_files.load(Ordering::Relaxed),
            total_folders: self.total_folders.load(Ordering::Relaxed),
            total_size: self.total_size.load(Ordering::Relaxed),
            max_depth: self.max_depth.load(Ordering::Relaxed),
            empty_folders,
            file_extensions: self.file_extensions.iter().map(|entry| (entry.key().clone(), *entry.value())).collect(),
            folder_names: self.folder_names.iter().map(|entry| (entry.key().clone(), *entry.value())).collect(),
            files_per_folder: self.files_per_folder.iter().map(|entry| (entry.key().clone(), *entry.value())).collect(),
            depth_distribution: self.depth_distribution.iter().map(|entry| (*entry.key(), *entry.value())).collect(),
        }
    }
}

/// Sequential statistics collector (original implementation)
#[derive(Debug)]
struct DirectoryStats {
    total_files: u64,
    total_folders: u64,
    total_size: u64,
    empty_folders: Vec<String>,
    file_extensions: HashMap<String, u64>,
    folder_names: HashMap<String, u64>,
    files_per_folder: HashMap<String, u64>,
    depth_distribution: HashMap<u32, u64>,
    max_depth: u32,
}

impl DirectoryStats {
    fn new() -> Self {
        Self {
            total_files: 0,
            total_folders: 0,
            total_size: 0,
            empty_folders: Vec::new(),
            file_extensions: HashMap::new(),
            folder_names: HashMap::new(),
            files_per_folder: HashMap::new(),
            depth_distribution: HashMap::new(),
            max_depth: 0,
        }
    }

    fn to_py_dict(&self, py: Python, root_path: &str) -> PyResult<PyObject> {
        let dict = PyDict::new(py);
        
        dict.set_item("root_path", root_path)?;
        
        // Summary
        let summary = PyDict::new(py);
        summary.set_item("total_files", self.total_files)?;
        summary.set_item("total_folders", self.total_folders)?;
        summary.set_item("total_size_bytes", self.total_size)?;
        summary.set_item("total_size_mb", (self.total_size as f64) / (1024.0 * 1024.0))?;
        summary.set_item("avg_files_per_folder", 
            if self.total_folders > 0 { 
                (self.total_files as f64) / (self.total_folders as f64) 
            } else { 
                0.0 
            })?;
        summary.set_item("max_depth", self.max_depth)?;
        summary.set_item("empty_folder_count", self.empty_folders.len())?;
        dict.set_item("summary", summary)?;
        
        dict.set_item("file_extensions", self.file_extensions.clone())?;
        dict.set_item("common_folder_names", self.folder_names.clone())?;
        dict.set_item("empty_folders", self.empty_folders.clone())?;
        dict.set_item("depth_distribution", self.depth_distribution.clone())?;
        
        // Convert files_per_folder to top folders by file count
        let mut top_folders: Vec<(String, u64)> = self.files_per_folder.iter()
            .map(|(k, v)| (k.clone(), *v))
            .collect();
        top_folders.sort_by(|a, b| b.1.cmp(&a.1));
        top_folders.truncate(10);
        dict.set_item("top_folders_by_file_count", top_folders)?;
        
        Ok(dict.into())
    }
}

/// Core analysis functions
mod analysis {
    use super::*;

    /// Check if a directory is empty
    pub fn is_empty_directory(entry: &DirEntry) -> bool {
        if !entry.file_type().is_dir() {
            return false;
        }
        
        match std::fs::read_dir(entry.path()) {
            Ok(mut entries) => entries.next().is_none(),
            Err(_) => false,
        }
    }

    /// Get normalized file extension
    pub fn get_file_extension(path: &Path) -> String {
        match path.extension() {
            Some(ext) => format!(".{}", ext.to_string_lossy().to_lowercase()),
            None => "<no extension>".to_string(),
        }
    }

    /// Calculate adjusted depth for consistent reporting
    pub fn calculate_adjusted_depth(depth: usize, root_depth: usize) -> u32 {
        if depth <= root_depth {
            0
        } else {
            (depth - root_depth) as u32
        }
    }

    /// Estimate directory size for parallel processing decisions
    pub fn estimate_directory_size(path: &Path, max_sample: usize) -> usize {
        let mut count = 0;
        
        if let Ok(entries) = std::fs::read_dir(path) {
            for entry in entries.take(max_sample) {
                if entry.is_ok() {
                    count += 1;
                }
            }
        }
        
        count
    }

    /// Get immediate subdirectories for parallel processing
    pub fn get_subdirectories(path: &Path, _config: &AnalysisConfig) -> Vec<PathBuf> {
        let mut subdirs = Vec::new();
        
        if let Ok(entries) = std::fs::read_dir(path) {
            for entry in entries.flatten() {
                if entry.file_type().map(|ft| ft.is_dir()).unwrap_or(false) {
                    subdirs.push(entry.path());
                }
            }
        }
        
        subdirs
    }
}

use analysis::*;

/// Sequential directory analysis engine
mod sequential {
    use super::*;

    pub fn analyze_directory_sequential(
        root_path: &Path,
        config: &AnalysisConfig,
    ) -> Result<DirectoryStats, String> {
        let mut stats = DirectoryStats::new();
        let mut walker = WalkDir::new(root_path).follow_links(config.follow_links);

        // Set max_depth on the walker if specified
        if let Some(max_d) = config.max_depth {
            walker = walker.max_depth((max_d + 1) as usize);
        }

        for entry in walker {
            let entry = match entry {
                Ok(entry) => entry,
                Err(_) => continue, // Skip inaccessible entries
            };

            let depth = entry.depth() as u32;

            // Skip entries that exceed our desired max_depth
            if let Some(max_d) = config.max_depth {
                if entry.file_type().is_dir() && depth > max_d {
                    continue;
                }
                if entry.file_type().is_file() && depth > max_d + 1 {
                    continue;
                }
            }

            // Adjust depth to match Python implementation
            let adjusted_depth = if depth == 0 { 0 } else { depth - 1 };

            stats.max_depth = stats.max_depth.max(adjusted_depth);
            *stats.depth_distribution.entry(adjusted_depth).or_insert(0) += 1;

            if entry.file_type().is_dir() {
                stats.total_folders += 1;

                // Check if empty
                if is_empty_directory(&entry) {
                    stats.empty_folders.push(entry.path().to_string_lossy().to_string());
                }

                // Count folder name
                if let Some(name) = entry.file_name().to_str() {
                    *stats.folder_names.entry(name.to_string()).or_insert(0) += 1;
                }

                // Initialize folder file count
                stats.files_per_folder.entry(
                    entry.path().to_string_lossy().to_string()
                ).or_insert(0);

            } else if entry.file_type().is_file() {
                stats.total_files += 1;

                // Get file extension
                let ext = get_file_extension(entry.path());
                *stats.file_extensions.entry(ext).or_insert(0) += 1;

                // Get file size
                if let Ok(metadata) = entry.metadata() {
                    stats.total_size += metadata.len();
                }

                // Count file in its parent directory
                if let Some(parent) = entry.path().parent() {
                    *stats.files_per_folder.entry(
                        parent.to_string_lossy().to_string()
                    ).or_insert(0) += 1;
                }
            }
        }

        Ok(stats)
    }
}

/// Parallel directory analysis engine
mod parallel {
    use super::*;

    pub fn analyze_directory_parallel(
        root_path: &Path,
        config: &AnalysisConfig,
    ) -> Result<DirectoryStats, String> {
        let stats = Arc::new(ParallelDirectoryStats::new());
        
        // First, analyze the root directory itself
        analyze_root_directory(root_path, &stats, config)?;
        
        // Get immediate subdirectories for parallel processing
        let subdirs = get_subdirectories(root_path, config);
        
        // Decide whether to use parallel processing
        let should_parallelize = subdirs.len() > 4 && 
            estimate_total_size(&subdirs) > config.parallel_threshold;
        
        if should_parallelize && subdirs.len() > 1 {
            // Process subdirectories in parallel
            subdirs.par_iter().for_each(|subdir| {
                let _ = analyze_subdirectory_recursive(subdir, &stats, config, 1);
            });
        } else {
            // Fall back to sequential processing for small directories
            for subdir in subdirs {
                let _ = analyze_subdirectory_recursive(&subdir, &stats, config, 1);
            }
        }
        
        Ok(stats.to_directory_stats())
    }

    fn analyze_root_directory(
        root_path: &Path,
        stats: &Arc<ParallelDirectoryStats>,
        _config: &AnalysisConfig,
    ) -> Result<(), String> {
        // Count the root directory itself
        if let Some(name) = root_path.file_name().and_then(|n| n.to_str()) {
            let is_empty = estimate_directory_size(root_path, 1) == 0;
            stats.add_folder(
                name.to_string(),
                is_empty,
                root_path.to_string_lossy().to_string(),
                0
            );
        }
        Ok(())
    }

    fn analyze_subdirectory_recursive(
        dir_path: &Path,
        stats: &Arc<ParallelDirectoryStats>,
        config: &AnalysisConfig,
        current_depth: u32,
    ) -> Result<(), String> {
        // Check depth limit
        if let Some(max_depth) = config.max_depth {
            if current_depth > max_depth {
                return Ok(());
            }
        }

        let mut walker = WalkDir::new(dir_path)
            .follow_links(config.follow_links)
            .min_depth(0);

        // Set max depth relative to this subdirectory
        if let Some(max_d) = config.max_depth {
            let remaining_depth = max_d.saturating_sub(current_depth);
            walker = walker.max_depth(remaining_depth as usize + 1);
        }

        for entry in walker {
            let entry = match entry {
                Ok(entry) => entry,
                Err(_) => continue,
            };

            let relative_depth = entry.depth() as u32;
            let absolute_depth = current_depth + relative_depth;

            if entry.file_type().is_dir() {
                let is_empty = is_empty_directory(&entry);
                
                if let Some(name) = entry.file_name().to_str() {
                    stats.add_folder(
                        name.to_string(),
                        is_empty,
                        entry.path().to_string_lossy().to_string(),
                        absolute_depth,
                    );
                }
            } else if entry.file_type().is_file() {
                let ext = get_file_extension(entry.path());
                let size = entry.metadata()
                    .map(|m| m.len())
                    .unwrap_or(0);
                
                let parent_path = entry.path().parent()
                    .map(|p| p.to_string_lossy().to_string())
                    .unwrap_or_default();

                stats.add_file(size, ext, parent_path);
            }
        }

        Ok(())
    }

    fn estimate_total_size(subdirs: &[PathBuf]) -> usize {
        subdirs.iter()
            .map(|path| estimate_directory_size(path, 100))
            .sum()
    }
}

/// Python interface functions
#[pyfunction]
fn analyze_directory_rust(root_path: &str, max_depth: Option<u32>) -> PyResult<PyObject> {
    analyze_directory_rust_with_config(root_path, max_depth, None)
}

#[pyfunction]
fn analyze_directory_rust_parallel(
    root_path: &str, 
    max_depth: Option<u32>,
    parallel_threshold: Option<usize>
) -> PyResult<PyObject> {
    analyze_directory_rust_with_config(root_path, max_depth, parallel_threshold)
}

fn analyze_directory_rust_with_config(
    root_path: &str,
    max_depth: Option<u32>,
    parallel_threshold: Option<usize>,
) -> PyResult<PyObject> {
    let root = Path::new(root_path);
    
    // Validate input
    if !root.exists() {
        return Err(pyo3::exceptions::PyValueError::new_err(
            format!("Path does not exist: {}", root_path)
        ));
    }
    
    if !root.is_dir() {
        return Err(pyo3::exceptions::PyValueError::new_err(
            format!("Path is not a directory: {}", root_path)
        ));
    }

    // Configure analysis
    let config = AnalysisConfig {
        max_depth,
        follow_links: false,
        parallel: parallel_threshold.is_some(),
        parallel_threshold: parallel_threshold.unwrap_or(1000),
    };

    // Choose analysis method based on configuration and directory size
    let stats = if should_use_parallel_analysis(root, &config) {
        parallel::analyze_directory_parallel(root, &config)
    } else {
        sequential::analyze_directory_sequential(root, &config)
    };

    let stats = stats.map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e))?;
    
    Python::with_gil(|py| stats.to_py_dict(py, root_path))
}

/// Intelligent decision making for when to use parallel processing
fn should_use_parallel_analysis(root: &Path, config: &AnalysisConfig) -> bool {
    if !config.parallel {
        return false;
    }

    // Quick heuristic: if the directory has many immediate subdirectories,
    // it's likely worth parallelizing
    let subdirs = get_subdirectories(root, config);
    
    // Use parallel processing if:
    // 1. We have at least 4 subdirectories to work with
    // 2. The estimated total size exceeds our threshold
    subdirs.len() >= 4 && {
        let estimated_size: usize = subdirs.iter()
            .take(10) // Sample first 10 subdirectories
            .map(|path| estimate_directory_size(path, 50))
            .sum();
        
        estimated_size * subdirs.len() / 10 > config.parallel_threshold
    }
}

#[pymodule]
fn filoma_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(analyze_directory_rust, m)?)?;
    m.add_function(wrap_pyfunction!(analyze_directory_rust_parallel, m)?)?;
    Ok(())
}
