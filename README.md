<p align="center">
    <img src="images/logo.png" alt="filoma logo" width="260">
</p>

<p align="center">
    <a href="https://badge.fury.io/py/filoma">
        <img src="https://badge.fury.io/py/filoma.svg" alt="PyPI version">
    </a>
    <img alt="Code style: ruff" src="https://img.shields.io/badge/code%20style-ruff-blueviolet">
    <img alt="Contributions welcome" src="https://img.shields.io/badge/contributions-welcome-brightgreen.svg?style=flat">
    <a href="https://github.com/filoma/filoma/actions/workflows/ci.yml">
        <img src="https://github.com/filoma/filoma/actions/workflows/ci.yml/badge.svg" alt="Tests">
    </a>
</p>

<p align="center">
  <strong>Fast, multi-backend file/directory profiling and data preparation for machine learning workflows.</strong>
</p>

<p align="center">
  <a href="docs/installation.md">Installation</a> •
  <a href="docs/quickstart.md">Quickstart</a> •
  <a href="docs/cookbook.md">Cookbook</a> •
  <a href="https://github.com/kalfasyan/filoma">Source Code</a>
</p>

---

`filoma` helps you analyze file directory trees, inspect file metadata, and prepare your data for exploration and modelling. It can achieve this blazingly fast using the best available backend (Rust, `fd`, or pure Python) ⚡🍃

---

## Key Features

- **🚀 High-Performance Backends**: Automatic selection of Rust, `fd`, or Python for the best performance.
- **📊 Rich Directory Analysis**: Get detailed statistics on file counts, extensions, sizes, and more.
- **🔍 Smart File Search**: Use regex and glob patterns to find files with `FdFinder`.
- **📈 DataFrame Integration**: Convert scan results to Polars DataFrames for powerful analysis.
- **🖼️ Image Profiling**: Extract metadata and statistics from various image formats.
- **🔀 ML-Ready Splits**: Create deterministic train/validation/test datasets with ease.

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
from filoma import probe_file

# Profile a file
file_info = probe_file("README.md")

print(f"Path: {file_info.path}")
print(f"Size: {file_info.size_str}")
print(f"Modified: {file_info.modified}")
```

For images, `probe_image` gives you additional details like shape and pixel statistics.

```python
from filoma import probe_image

# Profile an image
img_info = probe_image("images/logo.png")
print(f"Type: {img_info.file_type}")
print(f"Shape: {img_info.shape}")
```

### 2. Analyze a Directory

Scan an entire directory to get a high-level overview.

```python
from filoma import probe

# Analyze the current directory
analysis = probe('.')

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
from filoma import probe_to_df

# Scan a directory and get a DataFrame
df = probe_to_df('.')

print(df.head())
```

### 4. Enrich Your Data

Add more context to your DataFrame, like file depth and path components, with the `enrich()` method.

```python
# The DataFrame returned by probe_to_df is a filoma.DataFrame
# with extra capabilities.
df_enriched = df.enrich()

print(df_enriched.head())
```

### 5. Create ML-Ready Splits

`filoma` makes it easy to split your files into training, validation, and test sets for machine learning. You can even group files by parts of their path to prevent data leakage.

```python
from filoma import ml

# Split the data, grouping by parent directory
train, val, test = ml.split_data(df, how='parts', parts=(-2,), seed=42)

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
