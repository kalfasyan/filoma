
# filoma

[![PyPI version](https://badge.fury.io/py/filoma.svg)](https://badge.fury.io/py/filoma) ![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-blueviolet) ![Contributions welcome](https://img.shields.io/badge/contributions-welcome-brightgreen.svg?style=flat) [![Tests](https://github.com/kalfasyan/filoma/actions/workflows/ci.yml/badge.svg)](https://github.com/kalfasyan/filoma/actions/workflows/ci.yml)

`filoma` is a modular Python tool for profiling files, analyzing directory structures, and inspecting image data (e.g., .tif, .png, .npy, .zarr). It provides detailed reports on filename patterns, inconsistencies, file counts, empty folders, file system metadata, and image data statistics. The project is designed for easy expansion, testing, CI/CD, Dockerization, and database integration.

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

# For maximum performance, also install Rust toolchain:
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source ~/.cargo/env
# Then reinstall to build Rust extension:
uv add filoma --force  # or: uv pip install --force-reinstall filoma
```

> **Note**: Rust installation is optional. filoma works perfectly with pure Python, but gets 5-20x faster with Rust acceleration.

### Which Installation Method to Choose?

- **`uv add filoma`** → Use this if you have a `pyproject.toml` file (most Python projects)
- **`uv pip install filoma`** → Use for standalone scripts or when you don't want project dependency management
- **`pip install filoma`** → Traditional method for older Python environments

## Features
- **Directory analysis**: Comprehensive directory tree analysis including file counts, folder patterns, empty directories, extension analysis, size statistics, and depth distribution
- **📊 DataFrame support**: Build Polars DataFrames with all file paths for advanced analysis, filtering, and data manipulation
- **🦀 Rust acceleration**: Optional Rust backend for 5-20x faster directory analysis - **completely automatic and transparent!**
- **Image analysis**: Analyze .tif, .png, .npy, .zarr files for metadata, stats (min, max, mean, NaNs, etc.), and irregularities
- **File profiling**: System metadata (size, permissions, owner, group, timestamps, symlink targets, etc.)
- Modular, extensible codebase
- CLI entry point (planned)
- Ready for testing, CI/CD, Docker, and database integration

## 🚀 Automatic Performance Acceleration

`filoma` includes **automatic Rust acceleration** for directory analysis:

- **⚡ 5-20x faster** than pure Python (depending on directory size)
- **🔧 Zero configuration** - works automatically when Rust toolchain is available
- **🐍 Graceful fallback** - uses pure Python when Rust isn't available
- **📊 Transparent** - same API, same results, just faster!

### Quick Setup for Maximum Performance

```bash
# Install Rust (one-time setup)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source ~/.cargo/env

# Install filoma with Rust acceleration
uv add filoma          # For uv projects (recommended)
# or: uv pip install filoma  # For scripts/non-project environments
# or: pip install filoma     # Traditional method
# The Rust extension builds automatically during installation!
```

### Performance Examples

```python
from filoma.directories import DirectoryProfiler

profiler = DirectoryProfiler()
# The output shows which backend is used:
# "Directory Analysis: /path (🦀 Rust)" or "Directory Analysis: /path (🐍 Python)"

result = profiler.analyze("/large/directory")
# Typical speedups:
# - Small dirs (<1K files): 2-5x faster
# - Medium dirs (1K-10K files): 5-10x faster  
# - Large dirs (>10K files): 10-20x faster
```

**No code changes needed** - your existing code automatically gets faster! 🎉

### Quick Check: Is Rust Working?

```python
from filoma.directories import DirectoryProfiler

profiler = DirectoryProfiler()
result = profiler.analyze(".")

# Look for the 🦀 Rust emoji in the report title:
profiler.print_summary(result)
# Output shows: "Directory Analysis: . (🦀 Rust)" or "Directory Analysis: . (🐍 Python)"

# Or check programmatically:
print(f"Rust acceleration: {'✅ Active' if profiler.use_rust else '❌ Not available'}")
```

### Quick Installation Verification

```python
import filoma
from filoma.directories import DirectoryProfiler

# Check version and basic functionality
print(f"filoma version: {filoma.__version__}")

profiler = DirectoryProfiler()
print(f"Rust acceleration: {'✅ Active' if profiler.use_rust else '❌ Not available'}")
```

> **Pro tip**: 
> - **Working on a project?** → Use `uv add filoma` (manages your `pyproject.toml` automatically)
> - **Running standalone scripts?** → Use `uv pip install filoma` 
> - **Need compatibility?** → Use `pip install filoma`
> - **Want the fastest experience?** → Install [`uv`](https://github.com/astral-sh/uv) first!

## Simple Examples

### Directory Analysis
```python
from filoma.directories import DirectoryProfiler

# Automatically uses Rust acceleration when available (🦀 Rust)
# Falls back to Python implementation when needed (🐍 Python)
profiler = DirectoryProfiler()
result = profiler.analyze("/path/to/directory", max_depth=3)

# Print comprehensive report with rich formatting
# The report title shows which backend was used!
profiler.print_report(result)

# Or access specific data
print(f"Total files: {result['summary']['total_files']}")
print(f"Total folders: {result['summary']['total_folders']}")
print(f"Empty folders: {result['summary']['empty_folder_count']}")
print(f"File extensions: {result['file_extensions']}")
print(f"Common folder names: {result['common_folder_names']}")
```

### DataFrame Analysis (Advanced)
```python
from filoma.directories import DirectoryProfiler
from filoma import DataFrame

# Enable DataFrame building for advanced analysis
profiler = DirectoryProfiler(build_dataframe=True)
result = profiler.analyze("/path/to/directory")

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
df_with_stats = df.add_file_stats()  # size, timestamps, etc.

# Add depth information
df_with_depth = df.add_depth_column()

# Export for further analysis
df.save_csv("file_analysis.csv")
df.save_parquet("file_analysis.parquet")
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
- `src/filoma/directories/` — Directory analysis and structure profiling
- `src/filoma/images/` — Image profilers and analysis
- `src/filoma/files/` — File profiling (system metadata)
- `tests/` — Unit tests for all modules

## 🔧 Advanced: Rust Acceleration Details

For users who want to understand or customize the Rust acceleration:

- **How it works**: Core directory traversal implemented in Rust using `walkdir` crate
- **Compatibility**: Same API and output format as Python implementation
- **Setup guide**: See [RUST_ACCELERATION.md](RUST_ACCELERATION.md) for detailed setup instructions
- **Benchmarking**: Includes benchmark tool to test performance on your system
- **Development**: Hybrid architecture allows Python-only development while keeping Rust acceleration

### Manual Control (Advanced)

```python
# Force Python implementation (useful for debugging)
profiler = DirectoryProfiler(use_rust=False)

# Check which backend is being used
print(f"Using Rust: {profiler.use_rust}")

# Compare performance
import time
start = time.time()
result = profiler.analyze("/path/to/directory")
print(f"Analysis took {time.time() - start:.3f}s")
```

## Future TODO
- CLI tool for all features
- More image format support and advanced checks
- Database integration for storing reports
- Dockerization and deployment guides
- CI/CD workflows and badges

---
`filoma` is under active development. Contributions and suggestions are welcome!