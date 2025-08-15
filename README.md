
# filoma

[![PyPI version](https://badge.fury.io/py/filoma.svg)](https://badge.fury.io/py/filoma) ![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-blueviolet) ![Contributions welcome](https://img.shields.io/badge/contributions-welcome-brightgreen.svg?style=flat) [![Tests](https://github.com/kalfasyan/filoma/actions/workflows/ci.yml/badge.svg)](https://github.com/kalfasyan/filoma/actions/workflows/ci.yml)

`filoma` is a modular Python tool for profiling files, analyzing directory structures, and inspecting image data (e.g., .tif, .png, .npy, .zarr). It provides detailed reports on filename patterns, inconsistencies, file counts, empty folders, file system metadata, and image data statistics. 

**🚀 Triple-Backend Performance**: Choose from Python (universal), Rust (2.5x faster), or fd (competitive alternative) backends for optimal performance on any system.

## Installation

```bash
# 🚀 RECOMMENDED: Using uv (modern, fast Python package manager)
# Install uv first if you don't have it: curl -LsSf https://astral.sh/uv/install.sh | sh

# For uv projects (recommended - manages dependencies in pyproject.toml):
uv add filoma

# For scripts or non-project environments:
uv pip install filoma

# Traditional method:
pip install filoma

# 🔧 OPTIONAL: For maximum performance, install additional tools:

# Option 1: Rust toolchain (2.5x faster, auto-selected)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source ~/.cargo/env
# Then reinstall to build Rust extension:
uv add filoma --force  # or: uv pip install --force-reinstall filoma

# Option 2: fd command (competitive alternative)
# On Ubuntu/Debian:
sudo apt install fd-find
# On macOS:
brew install fd
# On other systems: https://github.com/sharkdp/fd#installation
```

> **Performance Tiers** (Cold Cache Reality): 
> - **Basic**: Pure Python (works everywhere, ~30K files/sec)
> - **Fast**: + fd command (competitive alternative, ~46K files/sec)  
> - **Fastest**: + Rust backend (best performance, ~70K files/sec, auto-selected)

### Which Installation Method to Choose?

- **`uv add filoma`** → Use this if you have a `pyproject.toml` file (most Python projects)
- **`uv pip install filoma`** → Use for standalone scripts or when you don't want project dependency management
- **`pip install filoma`** → Traditional method for older Python environments

## 🚀 Performance Backends

`filoma` automatically selects the best available backend for optimal performance:

### 🐍 Python Backend (Universal)
- **Always available** - works on any Python installation
- **Full compatibility** - complete feature set
- **Good performance** - suitable for most use cases

### 🦀 Rust Backend (Fastest Overall)
- **Best performance** - Fastest for both analysis and DataFrame building (cold cache)
- **Parallel processing** - automatic multi-threading for large directories  
- **Auto-selected** - chosen by default when available
- **2.5x faster** - than alternatives for real-world cold cache scenarios

### 🔍 fd Backend (Competitive Alternative)
- **Fast file discovery** - leverages the fast `fd` command-line tool
- **Advanced patterns** - supports both regex and glob patterns
- **Close second** - competitive performance, especially for discovery tasks
- **Hybrid approach** - fd for discovery + Python for analysis

### Quick Backend Check
```python
from filoma.directories import DirectoryProfiler

profiler = DirectoryProfiler()
result = profiler.analyze(".")

# Check which backend was used (shown in output):
profiler.print_summary(result)
# Shows: "Directory Analysis: . (🐍 Python)" or "🦀 Rust" or "🔍 fd"

# Check programmatically:
print(f"Rust available: {'✅' if profiler.use_rust else '❌'}")
print(f"fd available: {'✅' if profiler.fd_integration else '❌'}")
```

### Backend Selection
```python
# Automatic (recommended) - uses fastest available
profiler = DirectoryProfiler()

# Force specific backend based on your use case:
profiler_rust = DirectoryProfiler(search_backend="rust")     # Fastest overall (auto-selected)
profiler_fd = DirectoryProfiler(search_backend="fd")         # Competitive alternative  
profiler_python = DirectoryProfiler(search_backend="python") # Most comprehensive

# Performance comparison
import time
for name, prof in [("rust", profiler_rust), ("fd", profiler_fd), ("python", profiler_python)]:
    if prof.is_backend_available():
        start = time.time()
        result = prof.analyze("/path/to/directory")
        print(f"{name}: {time.time() - start:.3f}s")
```


## Features
- **🚀 Triple Backend System**: Automatically choose the best backend for your system:
  - **🐍 Python**: Universal compatibility, works everywhere
  - **🦀 Rust**: 2.5x faster directory analysis, auto-selected when available
  - **🔍 fd**: Competitive file discovery with regex/glob pattern support
- **Directory analysis**: Comprehensive directory tree analysis including file counts, folder patterns, empty directories, extension analysis, size statistics, and depth distribution
- **Progress bar & timing**: See real-time progress and timing for large directory scans, with beautiful terminal output (using `rich`)
- **📊 DataFrame support**: Build Polars DataFrames with all file paths for advanced analysis, filtering, and data manipulation
- **Image analysis**: Analyze .tif, .png, .npy, .zarr files for metadata, stats (min, max, mean, NaNs, etc.), and irregularities
- **File profiling**: System metadata (size, permissions, owner, group, timestamps, symlink targets, etc.)
- **Smart file search**: Advanced file discovery with the FdSearcher interface
- Modular, extensible codebase
- CLI entry point (planned)
- Ready for testing, CI/CD, Docker, and database integration
## Smart File Discovery

`filoma` provides powerful file search capabilities through the `FdSearcher` interface:

### Basic File Search
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

### Advanced Search Features
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

## Progress Bar & Timing Features

`filoma` provides real-time progress bars and timing for all backends, with beautiful terminal output using `rich`:

**Example:**

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

# Backend-specific progress indicators:
# 🐍 Python: Real-time file-by-file progress
# 🦀 Rust: Start/end progress (internal parallelism) 
# 🔍 fd: Discovery + analysis phases
```

**Performance Note:**
> The progress bar introduces minimal overhead (especially when updated every 100 items, as in the default implementation). For benchmarking or maximum speed, you can disable it with `show_progress=False`.


## 🚀 Performance & Benchmarks

`filoma` automatically selects the fastest available backend:

### Benchmark Test Environment
*All performance data measured on the following system:*

```
OS:         Linux x86_64 (Ubuntu-based)
Storage:    WD_BLACK SN770 2TB NVMe SSD (Sandisk Corp)
Filesystem: ext4 (non-NFS, local storage)
Memory:     High-speed access to NVMe storage
CPU:        Multi-core with parallel processing support
```

> **📊 Why This Matters**: SSD vs HDD performance can vary dramatically. NVMe SSDs provide 
> exceptional random I/O performance that benefits all backends. Network filesystems (NFS) 
> may show different characteristics. Your mileage may vary based on storage type.

> **📊 Network Storage Note**: In NFS environments, `fd` was often found to outperforms other backends. For such filesystems, consider forcing the `fd` backend with `DirectoryProfiler(search_backend="fd")` for optimal performance.

### ❄️ Cold Cache Methodology
**Critical**: All benchmarks use **cold cache** methodology to represent real-world performance:

```bash
# Before each test:
sync                                    # Flush buffers
echo 3 > /proc/sys/vm/drop_caches      # Clear filesystem cache
```

> **🔥 Cache Impact**: OS filesystem cache can make benchmarks **2-8x faster** but unrealistic. 
> Warm cache results don't represent first-time directory access. Our cold cache benchmarks 
> show realistic performance for real-world usage.

### File Discovery Performance (Fast Path)
*Cold cache benchmarks using `/usr` directory (~250K files)*

```
Backend      │ Time      │ Files/sec  
─────────────┼───────────┼────────────
Rust         │ 3.16s     │ 70,367     
fd           │ 4.80s     │ 46,244     
Python       │ 8.11s     │ 30,795     
```

### DataFrame Building Performance
*Cold cache benchmarks - Full metadata collection with DataFrame creation*
```
Backend      │ Time      │ Files/sec  
─────────────┼───────────┼────────────
Rust         │ 4.16s     │ 53,417     
fd           │ 4.80s     │ 46,219     
Python       │ 8.13s     │ 30,733     
```
> **🚀 Key Insights** (Cold Cache Reality): 
> - **Rust fastest overall** - Best performance for both file discovery and DataFrame building
> - **fd competitive** - Close second, excellent alternative when Rust isn't available
> - **Python most compatible** - Works by default, reliable fallback option
> - **Identical results** - All backends produce the same analysis output and metadata
> - **Cold vs warm cache** - Real performance is 2-8x slower than cached results
> - **Automatic selection** chooses the optimal backend for your use case

### Setup for Maximum Performance

```bash
# Step 1: Install filoma
uv add filoma  # or pip install filoma

# Step 2: Add Rust acceleration (optional but recommended)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source ~/.cargo/env
uv add filoma --force  # Rebuilds with Rust

# Step 3: Add fd for competitive alternative (optional)
# Ubuntu/Debian: sudo apt install fd-find
# macOS: brew install fd
# Windows: scoop install fd / choco install fd
```

### Performance Examples

```python
from filoma.directories import DirectoryProfiler
import time

# Automatic backend selection (recommended)
profiler = DirectoryProfiler()
start = time.time()
result = profiler.analyze("/large/directory")
print(f"Analysis completed in {time.time() - start:.3f}s")

# The output shows which backend was used:
profiler.print_summary(result)
# "Directory Analysis: /path (🦀 Rust)" ← Fastest (auto-selected)!
# "Directory Analysis: /path (🔍 fd)" ← Competitive alternative!  
# "Directory Analysis: /path (🐍 Python)" ← Reliable fallback
```

### 🧪 Benchmarking Best Practices

**For accurate performance testing:**

```python
import subprocess
import time
from filoma.directories import DirectoryProfiler

def clear_filesystem_cache():
    """Clear OS filesystem cache for realistic benchmarks."""
    subprocess.run(['sync'], check=True)
    subprocess.run(['sudo', 'tee', '/proc/sys/vm/drop_caches'], 
                   input='3\n', text=True, stdout=subprocess.DEVNULL, check=True)
    time.sleep(1)  # Let cache clear settle

# Cold cache benchmark (realistic)
clear_filesystem_cache()
profiler = DirectoryProfiler(search_backend="rust")
start = time.time()
result = profiler.analyze("/test/directory")
cold_time = time.time() - start

# Warm cache test (for comparison)
start = time.time()
result = profiler.analyze("/test/directory")  
warm_time = time.time() - start

print(f"Cold cache: {cold_time:.3f}s (realistic)")
print(f"Warm cache: {warm_time:.3f}s (cached, {cold_time/warm_time:.1f}x slower when cold)")
```

> **⚠️ Important**: Always use cold cache for realistic benchmarks. Warm cache results can be 
> 2-8x faster but don't represent real-world performance for first-time directory access.

### Installation Verification

```python
import filoma
from filoma.directories import DirectoryProfiler
from filoma.core import FdIntegration

# Check versions and availability
print(f"filoma version: {filoma.__version__}")

# Note: Progress bars auto-disable in IPython/Jupyter to avoid conflicts
profiler = DirectoryProfiler()
print(f"🦀 Rust backend: {'✅ Available' if profiler.use_rust else '❌ Not available'}")

fd = FdIntegration()
print(f"🔍 fd backend: {'✅ Available' if fd.is_available() else '❌ Not available'}")
if fd.is_available():
    print(f"   fd version: {fd.get_version()}")

# Quick performance test
result = profiler.analyze(".")
print(f"✨ Analysis completed using backend shown in output above")
print(f"📊 Found {result['summary']['total_files']} files, {result['summary']['total_folders']} folders")
```

> **Pro tip**: 
> - **Working on a project?** → Use `uv add filoma` (manages your `pyproject.toml` automatically)
> - **Running standalone scripts?** → Use `uv pip install filoma` 
> - **Need compatibility?** → Use `pip install filoma`
> - **Want the fastest experience?** → Install [`uv`](https://github.com/astral-sh/uv) first!

## Quick Start Examples

### Directory Analysis (Automatic Backend)
```python
from filoma.directories import DirectoryProfiler

# Automatically uses the fastest available backend
profiler = DirectoryProfiler()
result = profiler.analyze("/path/to/directory", max_depth=3)

# Beautiful terminal output shows which backend was used
profiler.print_summary(result)
# Example output: "Directory Analysis: /path (🔍 fd implementation)"

# Access specific data
print(f"📁 Total files: {result['summary']['total_files']}")
print(f"📂 Total folders: {result['summary']['total_folders']}")
print(f"🗂️ Empty folders: {result['summary']['empty_folder_count']}")
print(f"📄 File extensions: {result['file_extensions']}")
print(f"📋 Common folder names: {result['common_folder_names']}")
```

### Smart File Discovery
```python
from filoma.directories import FdSearcher

# High-level file search interface
searcher = FdSearcher()

# Find Python files with regex
python_files = searcher.find_files(pattern=r"\.py$", directory=".", max_depth=2)
print(f"🐍 Found {len(python_files)} Python files")

# Find multiple file types
code_files = searcher.find_by_extension(['py', 'rs', 'js', 'ts'], directory=".")
print(f"💻 Found {len(code_files)} code files")

# Find configuration files with glob patterns  
config_files = searcher.find_files(pattern="*.{json,yaml,toml}", use_glob=True)
print(f"⚙️ Found {len(config_files)} config files")

# Search in specific subdirectories (if they exist)
src_files = searcher.find_files(pattern=r"\.py$", directory="src", max_depth=3)
test_files = searcher.find_files(pattern=r"test.*\.py$", directory="tests")
```

### Low-Level fd Integration
```python
from filoma.core import FdIntegration

# Direct access to fd command
fd = FdIntegration()
if fd.is_available():
    print(f"🔍 Using fd {fd.get_version()}")
    
    # Fast file discovery
    all_files = fd.search(base_path=".", file_types=["f"])
    py_files = fd.search(pattern="\.py$", base_path=".", max_results=10)
    large_files = fd.search(pattern=".", file_types=["f"])  # Note: size filtering needs fd command support
    
    print(f"📊 Found {len(all_files)} total files")
else:
    print("❌ fd not available, install with: sudo apt install fd-find")
```

### DataFrame Analysis (Advanced)
```python
from filoma.directories import DirectoryProfiler
from filoma import DataFrame

# Enable DataFrame building for advanced analysis
# (Automatically uses fastest backend - fd for large directories)
profiler = DirectoryProfiler(build_dataframe=True)
result = profiler.analyze(".")

# Get the DataFrame with all file paths
df = profiler.get_dataframe(result)
print(f"Found {len(df)} paths")

# Add path components (parent, name, stem, suffix)
df_enhanced = df.add_path_components()
print(df_enhanced.head())

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

> **🚀 DataFrame Performance Tip**: filoma automatically selects the **Rust backend** for DataFrame building, which provides the fastest DataFrame creation. Rust consistently outperforms alternatives by 2.5x for both file discovery and DataFrame building tasks.

### Manual Backend Selection for DataFrames
```python
# Force Rust backend for maximum DataFrame performance (auto-selected by default)
profiler_rust = DirectoryProfiler(search_backend="rust", build_dataframe=True)

# Force specific backend for comparison
profiler_rust = DirectoryProfiler(backend="rust", build_dataframe=True)
profiler_python = DirectoryProfiler(backend="python", build_dataframe=True)

# Performance comparison
import time
for name, prof in [("fd", profiler_fd), ("rust", profiler_rust), ("python", profiler_python)]:
    if prof.is_backend_available():
        start = time.time()
        result = prof.analyze("/large/directory")
        df = prof.get_dataframe(result)
        print(f"{name} DataFrame: {len(df)} rows in {time.time() - start:.3f}s")
```

### File Profiling
```python
from filoma.files import FileProfiler
profiler = FileProfiler()
report = profiler.profile("/path/to/file.txt")
profiler.print_report(report)  # Rich table output in your terminal
# Output: (Rich table with file metadata and access rights)
```

### Image Analysis
```python
from filoma.images import PngProfiler
profiler = PngProfiler()
report = profiler.analyze("/path/to/image.png")
print(report)
# Output: {'shape': ..., 'dtype': ..., 'min': ..., 'max': ..., 'nans': ..., ...}
```

## Directory Analysis Features

The `DirectoryProfiler` provides comprehensive analysis of directory structures:

- **Statistics**: Total files, folders, size calculations, and depth distribution
- **File Extension Analysis**: Count and percentage breakdown of file types
- **Folder Patterns**: Identification of common folder naming patterns
- **Empty Directory Detection**: Find directories with no files or subdirectories
- **Depth Control**: Limit analysis depth with `max_depth` parameter
- **Rich Output**: Beautiful terminal reports with tables and formatting
- **📊 DataFrame Support**: Optional Polars DataFrame with all file paths for advanced analysis

### DataFrame Features
When enabled with `build_dataframe=True`, you get access to powerful data analysis capabilities:

- **Path Analysis**: Automatic extraction of path components (parent, name, stem, suffix)
- **File Statistics**: Size, modification times, creation times, file type detection
- **Advanced Filtering**: Filter by extensions, patterns, or custom conditions
- **Grouping & Aggregation**: Group by extension, directory, or custom fields
- **Export Options**: Save results as CSV, Parquet, or access the underlying Polars DataFrame
- **Performance**: Works with both Python and Rust implementations seamlessly

### Analysis Output Structure
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

### DataFrame API Reference

The `filoma.DataFrame` class provides:

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

## Project Structure
- `src/filoma/core/` — External tool integrations (fd integration, command runners)
- `src/filoma/directories/` — Directory analysis and structure profiling (3 backends: Python, Rust, fd)
- `src/filoma/images/` — Image profilers and analysis
- `src/filoma/files/` — File profiling (system metadata)
- `tests/` — All tests (unit, integration, and scripts) are in this folder

## Backend Architecture

### 🐍 Python Backend
- **Universal compatibility** - works on any Python installation
- **Full feature set** - complete directory analysis and statistics
- **Reliable fallback** - always available as a backup option

### 🦀 Rust Backend  
- **Best performance** - 2.5x faster than alternatives (cold cache tested)
- **Auto-selected** - chosen by default when available
- **Automatic build** - compiles during installation when Rust toolchain is detected
- **Same API** - drop-in replacement with identical output format

### 🔍 fd Backend
- **Competitive performance** - fast file discovery with the `fd` command-line tool
- **Hybrid approach** - fd for file discovery + Python for statistical analysis
- **Advanced patterns** - supports both regex and glob patterns with rich filtering options
- **Smart fallback** - automatically uses Python/Rust when fd is not available

All backends provide identical APIs and output formats, ensuring seamless interoperability.

## 🔧 Troubleshooting

### Backend Issues
```python
# Check what's available on your system
from filoma.directories import DirectoryProfiler
from filoma.core import FdIntegration

# Test each backend
profiler = DirectoryProfiler()
print(f"🐍 Python: Always available")
print(f"🦀 Rust: {'✅' if profiler.use_rust else '❌ - Install Rust toolchain'}")

fd = FdIntegration()
print(f"🔍 fd: {'✅' if fd.is_available() else '❌ - Install fd command'}")

# Test with a small directory
try:
    result = profiler.analyze(".", max_depth=1)
    print(f"✅ Basic analysis working")
except Exception as e:
    print(f"❌ Error: {e}")
```

### Installation Issues

**fd not found:**
```bash
# Ubuntu/Debian
sudo apt install fd-find

# macOS  
brew install fd

# Other systems - see: https://github.com/sharkdp/fd#installation
```

**Rust not building:**
```bash
# Install Rust toolchain
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source ~/.cargo/env

# Rebuild filoma with Rust support
pip install --force-reinstall filoma
```

**Performance issues:**
- Use `show_progress=False` for benchmarking
- Try `fast_path_only=True` for path discovery only
- Check which backend is being used in the output

## 🔧 Advanced Usage

### Backend Control & Comparison

```python
from filoma.directories import DirectoryProfiler
import time

# Test all available backends
backends = ["python", "rust", "fd"]
results = {}

for backend in backends:
    try:
        profiler = DirectoryProfiler(backend=backend)
        if profiler.is_backend_available():
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

### Manual Backend Selection

```python
# Force specific backends
profiler_python = DirectoryProfiler(backend="python", show_progress=False)
profiler_rust = DirectoryProfiler(backend="rust", show_progress=False)  
profiler_fd = DirectoryProfiler(backend="fd", show_progress=False)

# Disable progress for pure benchmarking
profiler_benchmark = DirectoryProfiler(show_progress=False, fast_path_only=True)

# Check which backend is actually being used
print(f"Python backend available: {profiler_python.is_backend_available()}")
print(f"Rust backend available: {profiler_rust.is_backend_available()}")
print(f"fd backend available: {profiler_fd.is_backend_available()}")
```

### Advanced fd Search Patterns

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
        # Note: size filtering would need fd command-line support
    )
    
    # Search hidden files
    hidden_files = fd.search(
        pattern=".*",
        search_hidden=True,
        max_results=100
    )
```

## Future Roadmap
- 🔄 CLI tool for all features with backend selection options
- 🔄 More image format support and advanced metadata checks
- 🔄 Database integration for storing and querying analysis reports
- 🔄 Dockerization and deployment guides with multi-backend support
- 🔄 Advanced fd features (size/time filtering, custom output formats)
- 🔄 Performance monitoring and automatic backend recommendation
- 🔄 Plugin system for custom profilers and analyzers

---
`filoma` is under active development. Contributions and suggestions are welcome!