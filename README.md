# filoma

[![PyPI version](https://badge.fury.io/py/filoma.svg)](https://badge.fury.io/py/filoma) ![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-blueviolet) ![Contributions welcome](https://img.shields.io/badge/contributions-welcome-brightgreen.svg?style=flat) [![Tests](https://github.com/kalfasyan/filoma/actions/workflows/ci.yml/badge.svg)](https://github.com/kalfasyan/filoma/actions/workflows/ci.yml)

**Fast, multi-backend Python tool for directory analysis and file profiling.**

Analyze directory structures, profile files, and inspect image data with automatic performance optimization through Rust, fd, or Python backends.

---

**Documentation**: [Installation](docs/installation.md) • [Backends](docs/backends.md) • [Advanced Usage](docs/advanced-usage.md) • [Benchmarks](docs/benchmarks.md)

**Source Code**: https://github.com/kalfasyan/filoma

---

## Quick Start

```bash
# Install
uv add filoma  # or: pip install filoma
```

```python
from filoma.directories import DirectoryProfiler

# Analyze any directory (automatically uses fastest backend)
profiler = DirectoryProfiler()
result = profiler.analyze("/path/to/directory")

# Beautiful terminal output
profiler.print_summary(result)
# Directory Analysis: /path (🦀 Rust) - 2.3s, 15,249 files, 1,847 folders

# Access data programmatically  
print(f"Files: {result['summary']['total_files']}")
print(f"Extensions: {result['file_extensions']}")
```

## Key Features

- **🚀 3 Performance Backends** - Automatic selection: Rust (2.5x faster), fd (competitive), Python (universal)
- **📊 Directory Analysis** - File counts, extensions, empty folders, depth distribution, size statistics
- **🔍 Smart File Search** - Advanced patterns with regex/glob support via FdSearcher
- **📈 DataFrame Support** - Build Polars DataFrames for advanced analysis and filtering
- **🖼️ Image Analysis** - Profile .tif, .png, .npy, .zarr files with metadata and statistics
- **📁 File Profiling** - System metadata, permissions, timestamps, symlink analysis
- **🎨 Rich Terminal Output** - Beautiful progress bars and formatted reports

## Examples

### Directory Analysis
```python
from filoma.directories import DirectoryProfiler

# Basic analysis
profiler = DirectoryProfiler()
result = profiler.analyze("/path/to/directory", max_depth=3)
profiler.print_summary(result)

# Access specific data
print(f"📁 Files: {result['summary']['total_files']}")
print(f"📂 Folders: {result['summary']['total_folders']}")
print(f"🗂️ Empty folders: {result['summary']['empty_folder_count']}")
print(f"📄 Extensions: {result['file_extensions']}")
```

### Smart File Search
```python
from filoma.directories import FdSearcher

searcher = FdSearcher()

# Find Python files
python_files = searcher.find_files(pattern=r"\.py$", max_depth=2)

# Find by multiple extensions
code_files = searcher.find_by_extension(['py', 'rs', 'js'], directory=".")

# Glob patterns
config_files = searcher.find_files(pattern="*.{json,yaml}", use_glob=True)
```

### DataFrame Analysis
```python
# Build DataFrame for advanced analysis
profiler = DirectoryProfiler(build_dataframe=True)
result = profiler.analyze(".")
df = profiler.get_dataframe(result)

# Add path components and analyze
df = df.add_path_components().add_file_stats()
python_files = df.filter_by_extension('.py')
df.save_csv("analysis.csv")
```

### File & Image Profiling
```python
from filoma.files import FileProfiler
from filoma.images import PngProfiler

# File metadata
file_profiler = FileProfiler()
report = file_profiler.profile("/path/to/file.txt")
file_profiler.print_report(report)

# Image analysis
img_profiler = PngProfiler()
img_report = img_profiler.analyze("/path/to/image.png")
print(img_report)  # Shape, dtype, stats, etc.
```

## Performance

**Automatic backend selection** for optimal speed:

| Backend | Speed | Use Case |
|---------|-------|----------|
| 🦀 **Rust** | ~70K files/sec | Large directories, DataFrame building |
| 🔍 **fd** | ~46K files/sec | Pattern matching, network filesystems |
| 🐍 **Python** | ~30K files/sec | Universal compatibility, reliable fallback |

*Cold cache benchmarks on NVMe SSD. See [benchmarks](docs/benchmarks.md) for detailed methodology.*

**System directories**: filoma automatically handles permission errors and falls back to Python implementation when needed for directories like `/proc`, `/sys`.

## Installation & Setup

See [installation guide](docs/installation.md) for:
- Quick setup with uv/pip
- Optional performance optimization (Rust/fd)
- Verification and troubleshooting

## Documentation

- **[Installation Guide](docs/installation.md)** - Setup and optimization
- **[Backend Architecture](docs/backends.md)** - How the multi-backend system works
- **[Advanced Usage](docs/advanced-usage.md)** - DataFrame analysis, pattern matching, backend control
- **[Performance Benchmarks](docs/benchmarks.md)** - Detailed performance analysis and methodology

## Project Structure

```
src/filoma/
├── core/          # Backend integrations (fd, Rust)
├── directories/   # Directory analysis with 3 backends
├── files/         # File profiling and metadata
└── images/        # Image analysis (.tif, .png, .npy, .zarr)
```

## License

This project is licensed under the MIT License.

## Contributing

Contributions welcome! Please check the [issues](https://github.com/kalfasyan/filoma/issues) for planned features and bug reports.

---

**filoma** - Fast, multi-backend file and directory analysis for Python.
