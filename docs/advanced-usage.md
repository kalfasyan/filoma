# Advanced Usage

## Profiler Quick Reference

This section shows the three main profilers (`DirectoryProfiler`, `FileProfiler`, `ImageProfiler`), short examples, and the most important constructor/probe arguments with notes about which backend(s) honor them.

DirectoryProfiler — high-level directory analysis (counts, extensions, empty folders, timing)

```python
from filoma.directories import DirectoryProfiler

profiler = DirectoryProfiler(
    search_backend='auto',   # 'auto'|'rust'|'fd'|'python'
    use_async=False,         # Rust async scanner (network-optimized)
    build_dataframe=True,    # collect paths into a DataFrame (Polars)
    show_progress=True,
)
result = profiler.probe('.')
profiler.print_summary(result)
```

Key arguments (what they do & which backend(s) support them):
- `search_backend` — choose preferred backend. Supported values: `rust`, `fd`, `python`, `auto` (default). All profilers use this to decide implementation.
- `use_async` — enable Rust async scanner (when `search_backend` allows Rust and tokio-enabled build). Backend: Rust (async only).
- `use_parallel` / `parallel_threshold` — prefer parallel Rust scanning when available; adjusts parallel decision heuristics. Backend: Rust (parallel only).
- `build_dataframe` — collect discovered paths into a Polars DataFrame for downstream analysis. Backend: works with any discovery backend; building is done in Python when using Rust/fd.
- `max_depth` — limit recursion depth. Honored by all backends.
- `follow_links` — whether to follow symlinks. Backend support: Rust (explicit flag), fd (discovery flag), Python (depends on os.walk behaviour but passed through by the profiler).
- `search_hidden` — include hidden files/dirs. Backend support: Rust, fd, Python (profiler passes preference).
- `no_ignore` — ignore .gitignore and similar ignore files (fd/Rust option). Backend support: fd, Rust.
- `threads` — number of threads forwarded to `fd` (if used). Backend: fd.
- `fast_path_only` — Rust-only mode to skip expensive metadata collection and only gather file paths (useful for very large trees).

Notes: when `search_backend='auto'` filoma chooses the most efficient backend available and applies fd-like defaults (follow hidden, do not respect ignore files) unless you explicitly override flags.

FileProfiler — probe a single file for metadata and optional hash

```python
from filoma.files import FileProfiler

filo = FileProfiler().probe('README.md', compute_hash=False)
print(filo.to_dict())
```

Key arguments:
- `compute_hash` (bool) — compute content hash (sha256). Supported by: FileProfiler (Python implementation) and internal Rust file profilers when enabled; computing a hash may be slower for large files.
- `follow_links` — when probing a path that is a symlink, whether to resolve it. Supported by: FileProfiler (behavior depends on implementation; FileProfiler forwards to low-level routines).

ImageProfiler — high-level entry point that dispatches to specialized image profilers (PNG, TIF, NPY, ZARR or in-memory numpy arrays)

```python
from filoma.images import ImageProfiler

# File path
img_report = ImageProfiler().probe('images/logo.png')

# Or pass a numpy array directly
import numpy as np
arr = np.zeros((64,64), dtype=np.uint8)
img_report2 = ImageProfiler().probe(arr)
```

Key arguments & notes:
- `path` or numpy array input — ImageProfiler accepts either a path-like (dispatches by extension) or an ndarray directly.
- `compute_stats` — compute pixel-level statistics (min/max/mean/std) and simple histograms. Supported by: image profilers implemented in Python; some heavy operations may call compiled helpers.
- `load_lazy` / `fast` — some backends/profilers may provide a fast/low-memory mode for very large images (TIF/ZARR). Backend support: varies by specific image profiler (Tif/Zarr profilers often support chunked/lazy reading).

Assumptions & compatibility
- The doc lists commonly available options; exact flag names and behavior are implemented in the specific profiler classes. When unspecified, `DirectoryProfiler` attempts to forward preferences to the chosen backend (`rust`/`fd`/`python`).
- If you'd like, I can add a small matrix table (argument vs backend) documenting the precise per-backend support for each flag.

## Smart File Discovery

### FdFinder Interface

```python
from filoma.directories import FdFinder

# Create searcher (automatically uses fd if available)
searcher = FdFinder()

# Find Python files
python_files = searcher.find_files(pattern=r"\.py$", path=".", max_depth=3)
print(f"Found {len(python_files)} Python files")

# Find files by extension
code_files = searcher.find_by_extension(['py', 'rs', 'js'], path=".")
image_files = searcher.find_by_extension(['.jpg', '.png', '.tif'], path=".")

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
recent_files = searcher.find_recent_files(changed_within="1d", path="/logs")

# Large files
large_files = searcher.find_large_files(min_size="1M", path="/data")
```

### Direct fd Integration

```python
from filoma.core import FdIntegration

# Low-level fd access
fd = FdIntegration()
if fd.is_available():
    print(f"fd version: {fd.get_version()}")
    
    # Regex pattern search
    py_files = fd.find(pattern=r"\.py$", path="/src", max_depth=2)
    
    # Glob pattern search  
    config_files = fd.find(pattern="*.json", use_glob=True, max_results=10)
    
    # Files only
    files = fd.find(file_types=["f"], max_depth=3)
    
    # Directories only
    dirs = fd.find(file_types=["d"], search_hidden=True)
```

## DataFrame Analysis

### Basic DataFrame Usage

```python
from filoma.directories import DirectoryProfiler

# Enable DataFrame building for advanced analysis
profiler = DirectoryProfiler(build_dataframe=True)
result = profiler.probe(".")

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

# Group and probe
extension_counts = df.group_by_extension()
directory_counts = df.group_by_directory()

# Add file statistics
df = df.add_file_stats_cols()  # size, timestamps, etc.

# Add depth information
df = df.add_depth_col()

# Export for further analysis
df.save_csv("file_analysis.csv")
df.save_parquet("file_analysis.parquet")
```

### DataFrame API Reference

```python
# Path manipulation
df.add_path_components()     # Add parent, name, stem, suffix columns
df.add_depth_col()        # Add directory depth column
df.add_file_stats_cols()          # Add size, timestamps, file type info

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
            result = profiler.probe("/test/directory")
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
    test_files = fd.find(
        pattern=r"test.*\.py$",
        path="/src",
        max_depth=3,
        case_sensitive=False
    )
    
    # Glob patterns with exclusions
    source_files = fd.find(
        pattern="*.{py,rs,js}",
        use_glob=True,
        exclude_patterns=["*test*", "*__pycache__*"],
        max_depth=5
    )
    
    # Find large files
    large_files = fd.find(
        pattern=".",
        file_types=["f"],
        absolute_paths=True
    )
    
    # Search hidden files
    hidden_files = fd.find(
        pattern=".*",
        search_hidden=True,
        max_results=100
    )
```

## Progress & Performance Features

```python
from filoma.directories import DirectoryProfiler

# Most profilers support progress bars via `show_progress=True` (behavior may
# differ depending on backend availability and interactive environment)
profiler = DirectoryProfiler(show_progress=True)
result = profiler.probe("/path/to/large/directory")
profiler.print_summary(result)

# Fast path only mode (just finds file paths, no metadata)
profiler_fast = DirectoryProfiler(show_progress=True, fast_path_only=True)
result_fast = profiler_fast.probe("/path/to/large/directory")
print(f"Found {result_fast['summary']['total_files']} files (fast path only)")

# Disable progress for benchmarking
profiler_benchmark = DirectoryProfiler(show_progress=False)
```

## Analysis Output Structure

```python
{
    "path": "/probed/path",
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
