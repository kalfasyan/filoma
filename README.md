<p align="center">
    <img src="images/logo.png" alt="filoma logo" width="260">
</p>  

[![PyPI version](https://badge.fury.io/py/filoma.svg)](https://badge.fury.io/py/filoma) ![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-blueviolet) ![Contributions welcome](https://img.shields.io/badge/contributions-welcome-brightgreen.svg?style=flat) [![Tests](https://github.com/filoma/filoma/actions/workflows/ci.yml/badge.svg)](https://github.com/filoma/filoma/actions/workflows/ci.yml)

**Fast, multi-backend Python tool for directory analysis and file profiling.**

Analyze directory structures, profile files, and inspect image data with automatic performance optimization through Rust (rayon, tokio, walkdir), [fd](https://github.com/sharkdp/fd) tool, or pure Python backends.

---

**Documentation**: [Installation](docs/installation.md) • [Backends](docs/backends.md) • [Advanced Usage](docs/advanced-usage.md) • [Benchmarks](docs/benchmarks.md)

**Source Code**: https://github.com/filoma/filoma

## Key Features


- **🚀 3 Performance Backends** - Automatic selection: Rust (*~2.3x faster* **\***), fd (competitive), Python (baseline)
- **📊 Directory Analysis** - File counts, extensions, empty folders, depth distribution, size statistics
- **🔍 Smart File Search** - Advanced patterns with regex/glob support via FdFinder
- **📈 DataFrame Support** - Build Polars DataFrames for advanced analysis and filtering
- **🖼️ Image Analysis** - Profile .tif, .png, .npy, .zarr files with metadata and statistics
- **📁 File Profiling** - System metadata, permissions, timestamps, symlink analysis
- **🎨 Rich Terminal Output** - Beautiful progress bars and formatted reports
- **🔀 ML-Friendly Splits** - Deterministic train/val/test splits grouped by path or filename tokens

**\*** *According to [benchmarks](docs/benchmarks.md)*  

---

## Quick Start  

With just a few lines of code, you can analyze directories, convert results to DataFrames, and profile files and images.

```bash
# Install
uv add filoma  # or: pip install filoma
```
#### Scan a directory and inspect the typed result:
```python
from filoma import probe

analysis = probe('.')
analysis.print_summary()
```
Output:
```text
Directory Analysis: /project (🦀 Rust (Parallel)) - 0.27s
Total Files: 17,330    Total Folders: 2,427    Analysis Time: 0.27 s
```
You can just as easily print a report of the full analysis:
```python
analysis.print_report()
```


#### Convert your scan results to a Polars DataFrame for further exploration:
```python
from filoma import probe_to_df

df = probe_to_df('.', use_rust=True)
print(df.select(['path','depth','is_file']).head(5))
```
Output (other columns omitted, e.g., *parent, name, stem, suffix, size_bytes, modified_time, created_time, is_dir*):
```text
┌────────────────────────┬──────┬─────────┐
│ path                   │ depth│ is_file │
├────────────────────────┼──────┼─────────┤
│ pyproject.toml         │ 1    │ True    │
│ scripts                │ 1    │ False   │
│ .pytest_cache          │ 1    │ False   │
│ .vscode                │ 1    │ False   │
│ Makefile               │ 1    │ True    │
└────────────────────────┴──────┴─────────┘
```
#### Profile individual files and images with one-liners, and get a dataclass with rich metadata:
```python
from filoma import probe_file, probe_image

filo = probe_file('README.md')
print(filo.path, filo.size)  

img = probe_image('images/logo.png')
print(img.file_type, getattr(img, 'shape', None))
```
Output:
```text
README.md 12.3 KB
png (1024, 256)
```
> **`filo`** includes attributes like `path`, `size`, `mode`, `owner`, `group`, `created`, `modified`, `is_dir`, `is_file`, `sha256`, and more, while **`img`** includes `file_type`, `shape`, `dtype`, `min`, `max`, `mean`, `nans`, `infs`, and more.


This minimal surface area (probe, probe_to_df, probe_file, probe_image) covers most needs: typed outputs, optional DataFrame workflows, and built-in pretty printers — ready for scripts, demos, and REPLs.



## Going Deeper (lower-level APIs)

### Super simple directory analysis  

Analyze a directory in one line and inspect the returned dataclass, or print a summary or full report:
```python
from filoma.directories import DirectoryProfiler

# Analyze a directory (returns DirectoryAnalysis object)
analysis = DirectoryProfiler().probe("/", max_depth=3)
analysis.print_summary()
analysis.print_report()
```
The DirectoryProfiler class offers extensive customization and control over backends, concurrency, and filtering. See [advanced usage](docs/advanced-usage.md) for details.

### Network filesystems — recommended approach

For NFS/SMB/cloud-fuse or other network-mounted filesystems, prefer a two-step strategy:

1. Try `fd` with multithreading first: fast discovery with controlled parallelism often gives the best performance with fewer issues.
    - Example: `DirectoryProfiler(use_fd=True, threads=8)` or set `search_backend='fd'`.
2. If you still need higher concurrency for high-latency mounts, enable the Rust async scanner as a secondary option (`use_async=True`) and tune `network_concurrency`, `network_timeout_ms`, and `network_retries`.

Short tips:
- Start with `use_fd` + a modest `threads` (4–16) and validate server load.
- Use async only when fd + multithreading isn't sufficient for your latency profile.
- Reduce concurrency if the server throttles or shows instability; increase timeout for very slow metadata calls.

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
df = df.add_path_components().add_file_stats_cols()
python_files = df.filter_by_extension('.py')
df.save_csv("analysis.csv")
```

### File & Image Profiling (one-liners)

File metadata and image analysis are easy with the top-level helpers:

```python
import filoma
import numpy as np

# File profiling (returns Filo dataclass)
filo = filoma.probe_file("/path/to/file.txt", compute_hash=False)
print(filo.path, filo.size)
print(filo.to_dict())

# Image profiling from file (dispatches to PNG/NPY/TIF/ZARR profilers)
img_report = filoma.probe_image("/path/to/image.png")
print(img_report.file_type, img_report.shape)

# Or analyze a numpy array directly
arr = np.zeros((64, 64), dtype=np.uint8)
img_report2 = filoma.probe_image(arr)
print(img_report2.to_dict())
```

### ML-Friendly Splitting  

Deterministic train/val/test splits grouped by filename or path-derived features (prevents related files leaking across sets).

```python
from filoma import probe_to_df, ml

# Create DataFrame from directory
df = probe_to_df('.') # DataFrame with 'path'
# A method can discover filename tokens that can be used for grouping
# e.g., 'sample1_imageA.png' -> token1='sample1', token2='imageA'
df = ml.discover_filename_features(df, sep='_', prefix=None)  # adds token1, token2, ...

# `auto_split` can now use these tokens to group files
train, val, test = ml.auto_split(df, train_val_test=(70,15,15))
print(len(train), len(val), len(test))

# Or group by parent folder instead (parts index -2)
train_p, val_p, test_p = ml.auto_split(df, how='parts', parts=(-2,), seed=42)

# You can also choose what return type you want (filoma, polars or pandas)
# with 'filoma' being the default, you can also make use of cool methods like `.add_file_stats_cols()`
# that uses the filoma file profiling under the hood
train_f, val_f, test_f = ml.auto_split(df, return_type='filoma')
```
Notes: hash-based & deterministic; if splits drift from the ratios requested, then a warning is logged. Use `verbose=False` to silence.  
To see some example usage, check out the [ml_examples notebook](notebooks/ml_examples.ipynb).

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

Contributions welcome! Please check the [issues](https://github.com/filoma/filoma/issues) for planned features and bug reports.

---

**filoma** - Fast, multi-backend file and directory analysis for Python.
