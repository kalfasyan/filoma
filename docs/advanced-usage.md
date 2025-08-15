# Advanced Usage

## Smart File Discovery

### FdSearcher Interface

```python
from filoma.directories import FdSearcher

# Create searcher (automatically uses fd if available)
searcher = FdSearcher()

# Find Python files
python_files = searcher.find_files(pattern=r"\.py$", directory=".", max_depth=3)
print(f"Found {len(python_files)} Python files")

# Find files by extension
code_files = searcher.find_by_extension(['py', 'rs', 'js'], directory=".")
image_files = searcher.find_by_extension(['.jpg', '.png', '.tif'], directory=".")

# Find directories
test_dirs = searcher.find_directories(pattern="test", max_depth=2)
```

### Advanced Search Patterns

```python
# Search with glob patterns
config_files = searcher.find_files(pattern="*.config.*", use_glob=True)

# Search hidden files
hidden_files = searcher.find_files(pattern=".*", hidden=True)

# Case-insensitive search
readme_files = searcher.find_files(pattern="readme", case_sensitive=False)

# Recent files (if fd supports time filters)
recent_files = searcher.find_recent_files(timeframe="1d", directory="/logs")

# Large files
large_files = searcher.find_large_files(size=">1M", directory="/data")
```

### Direct fd Integration

```python
from filoma.core import FdIntegration

# Low-level fd access
fd = FdIntegration()
if fd.is_available():
    print(f"fd version: {fd.get_version()}")
    
    # Regex pattern search
    py_files = fd.search(pattern=r"\.py$", base_path="/src", max_depth=2)
    
    # Glob pattern search  
    config_files = fd.search(pattern="*.json", use_glob=True, max_results=10)
    
    # Files only
    files = fd.search(file_types=["f"], max_depth=3)
    
    # Directories only
    dirs = fd.search(file_types=["d"], search_hidden=True)
```

## DataFrame Analysis

### Basic DataFrame Usage

```python
from filoma.directories import DirectoryProfiler

# Enable DataFrame building for advanced analysis
profiler = DirectoryProfiler(build_dataframe=True)
result = profiler.analyze(".")

# Get the DataFrame with all file paths
df = profiler.get_dataframe(result)
print(f"Found {len(df)} paths")

# Add path components (parent, name, stem, suffix)
df_enhanced = df.add_path_components()
print(df_enhanced.head())
```

### Advanced DataFrame Operations

```python
# Filter by file type
python_files = df.filter_by_extension('.py')
image_files = df.filter_by_extension(['.jpg', '.png', '.tif'])

# Group and analyze
extension_counts = df.group_by_extension()
directory_counts = df.group_by_directory()

# Add file statistics
df = df.add_file_stats()  # size, timestamps, etc.

# Add depth information
df = df.add_depth_column()

# Export for further analysis
df.save_csv("file_analysis.csv")
df.save_parquet("file_analysis.parquet")
```

### DataFrame API Reference

```python
# Path manipulation
df.add_path_components()     # Add parent, name, stem, suffix columns
df.add_depth_column()        # Add directory depth column
df.add_file_stats()          # Add size, timestamps, file type info

# Filtering
df.filter_by_extension('.py')              # Filter by single extension
df.filter_by_extension(['.jpg', '.png'])   # Filter by multiple extensions
df.filter_by_pattern('test')               # Filter by path pattern

# Analysis
df.group_by_extension()      # Group and count by file extension
df.group_by_directory()      # Group and count by parent directory

# Export
df.save_csv("analysis.csv")           # Export to CSV
df.save_parquet("analysis.parquet")   # Export to Parquet
df.to_polars()                        # Get underlying Polars DataFrame
```

## Backend Control & Comparison

```python
from filoma.directories import DirectoryProfiler
import time

# Test all available backends
backends = ["python", "rust", "fd"]
results = {}

for backend in backends:
    try:
        profiler = DirectoryProfiler(search_backend=backend)
        # Check if the specific backend is available
        available = ((backend == "rust" and profiler.is_rust_available()) or
                    (backend == "fd" and profiler.is_fd_available()) or
                    (backend == "python"))  # Python always available
        if available:
            start = time.time()
            result = profiler.analyze("/test/directory")
            elapsed = time.time() - start
            results[backend] = {
                'time': elapsed,
                'files': result['summary']['total_files'],
                'available': True
            }
            print(f"✅ {backend}: {elapsed:.3f}s - {result['summary']['total_files']} files")
        else:
            print(f"❌ {backend}: Not available")
    except Exception as e:
        print(f"⚠️ {backend}: Error - {e}")

# Find the fastest
if results:
    fastest = min(results.keys(), key=lambda k: results[k]['time'])
    print(f"🏆 Fastest backend: {fastest}")
```

## Manual Backend Selection

```python
# Force specific backends
profiler_python = DirectoryProfiler(search_backend="python", show_progress=False)
profiler_rust = DirectoryProfiler(search_backend="rust", show_progress=False)  
profiler_fd = DirectoryProfiler(search_backend="fd", show_progress=False)

# Disable progress for pure benchmarking
profiler_benchmark = DirectoryProfiler(show_progress=False, fast_path_only=True)

# Check which backend is actually being used
print(f"Python backend available: True")  # Always available
print(f"Rust backend available: {profiler_rust.is_rust_available()}")
print(f"fd backend available: {profiler_fd.is_fd_available()}")
```

## Complex fd Search Patterns

```python
from filoma.core import FdIntegration

fd = FdIntegration()

if fd.is_available():
    # Complex regex patterns
    test_files = fd.search(
        pattern=r"test.*\.py$",
        base_path="/src",
        max_depth=3,
        case_sensitive=False
    )
    
    # Glob patterns with exclusions
    source_files = fd.search(
        pattern="*.{py,rs,js}",
        use_glob=True,
        exclude_patterns=["*test*", "*__pycache__*"],
        max_depth=5
    )
    
    # Find large files
    large_files = fd.search(
        pattern=".",
        file_types=["f"],
        absolute_paths=True
    )
    
    # Search hidden files
    hidden_files = fd.search(
        pattern=".*",
        search_hidden=True,
        max_results=100
    )
```

## Progress & Performance Features

```python
from filoma.directories import DirectoryProfiler

# All backends support progress bars
profiler = DirectoryProfiler(show_progress=True)
result = profiler.analyze("/path/to/large/directory")
profiler.print_summary(result)

# Fast path only mode (just finds file paths, no metadata)
profiler_fast = DirectoryProfiler(show_progress=True, fast_path_only=True)
result_fast = profiler_fast.analyze("/path/to/large/directory")
print(f"Found {result_fast['summary']['total_files']} files (fast path only)")

# Disable progress for benchmarking
profiler_benchmark = DirectoryProfiler(show_progress=False)
```

## Analysis Output Structure

```python
{
    "root_path": "/analyzed/path",
    "summary": {
        "total_files": 150,
        "total_folders": 25,
        "total_size_bytes": 1048576,
        "total_size_mb": 1.0,
        "avg_files_per_folder": 6.0,
        "max_depth": 3,
        "empty_folder_count": 2
    },
    "file_extensions": {".py": 45, ".txt": 30, ".md": 10},
    "common_folder_names": {"src": 3, "tests": 2, "docs": 1},
    "empty_folders": ["/path/to/empty1", "/path/to/empty2"],
    "top_folders_by_file_count": [("/path/with/most/files", 25)],
    "depth_distribution": {0: 1, 1: 5, 2: 12, 3: 7},
    "dataframe": filoma.DataFrame  # When build_dataframe=True
}
```
