<p align="center">
    <img src="images/logo.png" alt="filoma logo" width="260">
</p>  

<h1 align="center">filoma</h1>

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
profiler = DirectoryProfiler()
res = profiler.probe("/")
profiler.print_summary(res)
```
Example output:

```text
Directory Analysis: / (🦀 Rust (Parallel)) - 29.56s
┌───────────────────────────┬──────────────────┐
│ Metric                    │ Value            │
├───────────────────────────┼──────────────────┤
│ Total Files               │ 2,186,785        │
│ Total Folders             │ 209,401          │
│ Total Size                │ 135,050,621.82 MB│
│ Average Files per Folder  │ 10.44            │
│ Maximum Depth             │ 21               │
│ Empty Folders             │ 7,930            │
│ Analysis Time             │ 29.56 s          │
│ Processing Speed          │ 81,074 items/sec │
└───────────────────────────┴──────────────────┘
```

## Key Features


- **🚀 3 Performance Backends** - Automatic selection: Rust (*~2.3x faster* **\***), fd (competitive), Python (baseline)
- **📊 Directory Analysis** - File counts, extensions, empty folders, depth distribution, size statistics
- **🔍 Smart File Search** - Advanced patterns with regex/glob support via FdFinder
- **📈 DataFrame Support** - Build Polars DataFrames for advanced analysis and filtering
- **🖼️ Image Analysis** - Profile .tif, .png, .npy, .zarr files with metadata and statistics
- **📁 File Profiling** - System metadata, permissions, timestamps, symlink analysis
- **🎨 Rich Terminal Output** - Beautiful progress bars and formatted reports

**\*** *According to [benchmarks](docs/benchmarks.md)*

## Examples

### Directory Analysis

The simplest way to probe a directory and print a summary:
```python
from filoma.directories import DirectoryProfiler

profiler = DirectoryProfiler()
res = profiler.probe("/", max_depth=3)
profiler.print_summary(res)
```

### Async (opt-in) — good for network filesystems

If traversing NFS/SMB, remote mounts, cloud-fuse, etc., enable async mode to parallelize filesystem calls and improve throughput.

```python
# Async (opt‑in) scanning for network / high‑latency filesystems
# Enable when traversing NFS/SMB, remote mounts, cloud-fuse, etc.
from filoma.directories import DirectoryProfiler

profiler = DirectoryProfiler(
    use_async=True,
    network_concurrency=32,    # Parallel in-flight filesystem ops
    network_timeout_ms=3000,   # Per op timeout (ms)
    network_retries=2          # Retries for transient errors
)

result = profiler.probe("/mnt/nfs/share")
profiler.print_summary(result)
```

Tips:
- Lower network_concurrency if the server throttles you; raise for high-latency links.
- Increase network_timeout_ms for very slow metadata calls.
- Retries help with flaky mounts; set to 0 for strict mode.
- Fallback: omit use_async for local SSDs (sync is usually faster there).

### Smart File Search

The `FdFinder` class provides advanced file searching with regex and glob support, leveraging the high-performance `fd` tool when available.

```python
from filoma.directories import FdFinder

searcher = FdFinder()

# Find Python files
python_files = searcher.find_files(pattern=r"\.py$", max_depth=2)

# Find by multiple extensions
code_files = searcher.find_by_extension(['py', 'rs', 'js'], path=".")

# Glob patterns
config_files = searcher.find_files(pattern="*.{json,yaml}", use_glob=True)
```

### DataFrame Analysis

`filoma` can build Polars DataFrames for advanced analysis and filtering, allowing you to leverage the full power of Polars for downstream tasks.

```python
# Build DataFrame for advanced analysis
profiler = DirectoryProfiler(build_dataframe=True)
result = profiler.probe(".")
df = profiler.get_dataframe(result)

# Add path components and probe
df = df.add_path_components().add_file_stats()
python_files = df.filter_by_extension('.py')
df.save_csv("analysis.csv")
```

### File & Image Profiling
Individual file profiling with metadata and image analysis:
```python
from filoma.files import FileProfiler
from filoma.images import PngProfiler

# File metadata
file_profiler = FileProfiler()

# returns a `Filo` dataclass with attribute access
#    `compute_hash=True` will compute a SHA256 fingerprint (optional/expensive)
filo = file_profiler.probe("/path/to/file.txt", compute_hash=True)
print(filo)               # dataclass repr; access fields like filo.path, filo.sha256
print(filo.sha256)        # full SHA256 (if computed)
print(filo.to_dict())     # convert to plain dict

# Image analysis
img_profiler = PngProfiler()
img_report = img_profiler.probe("/path/to/image.png")
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

**System directories**: filoma automatically handles permission errors for directories like `/proc`, `/sys`.

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

Shield: [![CC BY 4.0][cc-by-shield]][cc-by]

This work is licensed under a
[Creative Commons Attribution 4.0 International License][cc-by].

[![CC BY 4.0][cc-by-image]][cc-by]

[cc-by]: http://creativecommons.org/licenses/by/4.0/
[cc-by-image]: https://i.creativecommons.org/l/by/4.0/88x31.png
[cc-by-shield]: https://img.shields.io/badge/License-CC%20BY%204.0-lightgrey.svg

## Contributing

Contributions welcome! Please check the [issues](https://github.com/kalfasyan/filoma/issues) for planned features and bug reports.

---

**filoma** - Fast, multi-backend file and directory analysis for Python.
