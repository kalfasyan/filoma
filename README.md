<p align="center">
    <img src="images/logo.png" alt="filoma logo" width="260">
</p>

<p align="center">
    <a href="https://badge.fury.io/py/filoma">
        <img src="https://badge.fury.io/py/filoma.svg" alt="PyPI version">
    </a>
    <a href="https://filoma.readthedocs.io/en/latest/">
        <img src="https://readthedocs.org/projects/filoma/badge/?version=latest" alt="Documentation Status">
    </a>
    <img alt="Code style: ruff" src="https://img.shields.io/badge/code%20style-ruff-blueviolet">
    <img alt="Contributions welcome" src="https://img.shields.io/badge/contributions-welcome-brightgreen.svg?style=flat">
    <a href="https://github.com/kalfasyan/filoma/actions/workflows/ci.yml">
        <img src="https://github.com/kalfasyan/filoma/actions/workflows/ci.yml/badge.svg" alt="Tests">
    </a>
</p>

<p align="center">
  <strong>Fast, multi-backend file/directory profiling and data preparation for machine learning workflows.</strong>
</p>

<p align="center">
  <a href="docs/installation.md">Installation</a> •
  <a href="https://filoma.readthedocs.io/en/latest/">Documentation</a> •
  <a href="docs/cli.md">Interactive CLI</a> •
  <a href="docs/quickstart.md">Quickstart</a> •
  <a href="docs/cookbook.md">Cookbook</a> •
  <a href="https://github.com/kalfasyan/filoma">Source Code</a>
</p>

---

`filoma` helps you analyze file directory trees, inspect file metadata, and prepare your data for exploration and modelling. It can achieve this blazingly fast using the best available backend (Rust, [`fd`](https://github.com/sharkdp/fd), or pure Python) ⚡🍃

---
## CLI Demo
<img src="images/demo.gif" alt="filoma CLI screenshot" width="800">

## Key Features
- **🖥️ Interactive CLI**: Beautiful terminal interface for filesystem exploration and DataFrame analysis [📖 **CLI Documentation →**](docs/cli.md)
- **🚀 High-Performance Backends**: Automatic selection of Rust, `fd`, or Python for the best performance.
- **📊 Rich Directory Analysis**: Get detailed statistics on file counts, extensions, sizes, and more.
- **🔍 Smart File Search**: Use regex and glob patterns to find files with `FdFinder`.
- **📈 DataFrame Integration**: Convert scan results to [Polars](https://github.com/pola-rs/polars) (or [pandas](https://github.com/pandas-dev/pandas)) DataFrames for powerful analysis.
- **🖼️ File/Image Profiling**: Extract metadata and statistics from various file formats.
- **🔀 ML-Ready Splits**: Create deterministic train/validation/test datasets with ease.

  
## Scope of `filoma`  
<img src="images/flow.png" alt="filoma workflow diagram" width="400">  

## Feature Highlights
Quick, copyable examples showing filoma's standout capabilities and where to learn more.

- **Automatic multi-backend scanning:** filoma picks the fastest available backend (Rust → `fd` → pure Python). You can also force a backend for reproducibility. See the backends docs: `docs/backends.md`.

```python
import filoma as flm

# filoma will pick Rust > fd > Python depending on availability
analysis = flm.probe('.')
analysis.print_summary()
```

- **Polars-first DataFrame wrapper & enrichment:** Returns a `filoma.DataFrame` (Polars) with helpers to add path components, depth, and file stats for immediate analysis. Docs: `docs/dataframe.md`.

```python
df = flm.probe_to_df('.', enrich=True)  # returns a filoma.DataFrame
print(df.head())
```

- **Ultra-fast discovery with `fd`:** When `fd` is available filoma uses it for very fast file discovery. Advanced usage and patterns: `docs/advanced-usage.md`.

```python
if flm.fd.is_available():
    files = flm.fd.find(pattern=r"\\.py$", path='src', max_depth=3)
    print(len(files), 'python files found')
```

- **ML-ready, deterministic splits:** Group-aware, reproducible train/validation/test splitting to avoid leakage. See `docs/ml.md` for grouping options and examples.

```python
df = flm.probe_to_df('.', enrich=False)
train, val, test = flm.ml.split_data(df, train_val_test=(70,15,15), seed=42)
```

- **Lightweight, lazy top-level API:** Importing `filoma` is cheap; heavy dependencies load only when used. Quickstart and one-line helpers: `docs/quickstart.md`.

```python
info = flm.probe_file('README.md')
df = flm.probe_to_df('.')
```

## Installation

Install `filoma` using `uv` or `pip`:
```bash
uv pip install filoma
```

---

## Workflow Demo

This guide follows a typical `filoma` workflow, from basic file profiling to creating machine learning datasets.

### 1. Profile a Single File

Start by inspecting a single file. `filoma` provides a detailed dataclass with metadata.

```python
import filoma as flm

# Profile a file
file_info = flm.probe_file("README.md")

print(f"Path: {file_info.path}")
print(f"Size: {file_info.size_str}")
print(f"Modified: {file_info.modified}")
```

For images, `probe_image` gives you additional details like shape and pixel statistics.

```python
# Profile an image
img_info = flm.probe_image("images/logo.png")
print(f"Type: {img_info.file_type}")
print(f"Shape: {img_info.shape}")
```

### 2. Analyze a Directory

Scan an entire directory to get a high-level overview.

```python
# Analyze the current directory
analysis = flm.probe('.')

# Print a summary report
analysis.print_summary()
```
```text
Directory Analysis: /project (🦀 Rust (Parallel)) - 0.27s
Total Files: 17,330    Total Folders: 2,427    Analysis Time: 0.27 s
```

### 3. Convert to a DataFrame

For detailed analysis, convert the scan results into a Polars DataFrame.

```python
# Scan a directory and get a DataFrame
df = flm.probe_to_df('.')

print(df.head())
```

### 4. Enrich Your Data

Add more context to your DataFrame, like file depth and path components, with the `enrich()` method.

```python
# The DataFrame returned by flm.probe_to_df is a filoma.DataFrame
# with extra capabilities.
df_enriched = df.enrich()

print(df_enriched.head())
```

### 5. Create ML-Ready Splits

`filoma` makes it easy to split your files into training, validation, and test sets for machine learning. You can even group files by parts of their path to prevent data leakage.

```python
# Split the data, grouping by parent directory
train, val, test = flm.ml.split_data(df, how='parts', parts=(-2,), seed=42)

print(f"Train: {len(train)}, Validation: {len(val)}, Test: {len(test)}")
```

---

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

**filoma** - Fast, multi-backend file/directory profiling and data preparation for Python.
