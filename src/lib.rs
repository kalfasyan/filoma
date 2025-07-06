use pyo3::prelude::*;
use pyo3::types::PyDict;
use std::collections::HashMap;
use std::path::Path;
use walkdir::{DirEntry, WalkDir};

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

fn is_empty_directory(entry: &DirEntry) -> bool {
    if !entry.file_type().is_dir() {
        return false;
    }
    
    match std::fs::read_dir(entry.path()) {
        Ok(mut entries) => entries.next().is_none(),
        Err(_) => false,
    }
}

fn get_file_extension(path: &Path) -> String {
    match path.extension() {
        Some(ext) => format!(".{}", ext.to_string_lossy().to_lowercase()),
        None => "<no extension>".to_string(),
    }
}

#[pyfunction]
fn analyze_directory_rust(root_path: &str, max_depth: Option<u32>) -> PyResult<PyObject> {
    let root = Path::new(root_path);
    
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
    
    let mut stats = DirectoryStats::new();
    
    let mut walker = WalkDir::new(root).follow_links(false);
    
    // Set max_depth on the walker if specified
    // We need to add 1 because walkdir counts the root as depth 0,
    // but we want to include files at the max_depth level
    if let Some(max_d) = max_depth {
        walker = walker.max_depth((max_d + 1) as usize);
    }
    
    for entry in walker {
        let entry = match entry {
            Ok(entry) => entry,
            Err(_) => continue, // Skip inaccessible entries
        };
        
        let depth = entry.depth() as u32;
        
        // Skip entries that exceed our desired max_depth
        // (we set walkdir max_depth to max_depth+1 to include files at max_depth)
        if let Some(max_d) = max_depth {
            // For directories, skip if beyond max_depth
            // For files, skip if their parent directory would be beyond max_depth
            if entry.file_type().is_dir() && depth > max_d {
                continue;
            }
            if entry.file_type().is_file() && depth > max_d + 1 {
                continue;
            }
        }
        
        // Adjust depth to match Python implementation (relative path depth)
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
            
            // We'll count files per folder as we encounter files, not here
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
    
    Python::with_gil(|py| stats.to_py_dict(py, root_path))
}

#[pymodule]
fn filoma_core(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(analyze_directory_rust, m)?)?;
    Ok(())
}
