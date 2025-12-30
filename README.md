<p align="center">
    <img src="docs/assets/images/logo.png" alt="filoma logo" width="260">
</p>

<p align="center">
    <a href="https://badge.fury.io/py/filoma">
        <img src="https://badge.fury.io/py/fil fury.io/py/filoma.svg" alt="PyPI version">
    </a>
    <a href="https://filoma.readthedocs.io/en/latest/">
        <img src="https://readthedocs.org/projects/filoma/badge/?version=latest" alt="Documentation Status">
    </a>
    <img alt="Code style: ruff" src="https://img.shields.io/badge/code%20style-ruff-blueviolet">
    <a href="https://github.com/PyCQA/bandit">
        <img src="https://img.shields.io/badge/security-bandit-yellow.svg" alt="Security: bandit">
    </a>
    <img alt="Contributions welcome" src="https://img.shields.io/badge/contributions-welcome-brightgreen.svg?style=flat">
    <a href="https://github.com/kalfasyan/filoma/actions/workflows/ci.yml">
        <img src="https://github.com/kalfasyan/filoma/actions/workflows/ci.yml/badge.svg" alt="Tests">
    </a>
</p>

<p align="center">
  <strong>Fast, multi-backend file/directory profiling and data preparation.</strong>
</p>

> 🚧 **Filoma is under active development** — new features are being added regularly, APIs may evolve, and I'm always looking for feedback! Think of it as your friendly neighborhood file analysis toolkit that's still learning new tricks. Contributions, bug reports, and feature requests are more than welcome! 🎉

<p align="center">
  <a href="docs/installation.md">Installation</a> •
  <a href="https://filoma.readthedocs.io/en/latest/">Documentation</a> •
  <a href="docs/cli.md">Interactive CLI</a> •
  <a href="docs/quickstart.md">Quickstart</a> •
  <a href="docs/cookbook.md">Cookbook</a> •
  <a href="https://github.com/kalfasyan/filoma/blob/main/notebooks/roboflow_demo.ipynb">Roboflow Dataset Demo</a> •
  <a href="https://github.com/kalfasyan/filoma">Source Code</a>
</p>

---

`filoma` helps you analyze file directory trees, inspect file metadata, and prepare your data for exploration. It can achieve this blazingly fast using the best available backend (Rust, [`fd`](https://github.com/sharkdp/fd), or pure Python) ⚡🍃



## Key Features
- **🖥️ Interactive CLI**: Beautiful terminal interface for filesystem exploration and DataFrame analysis [📖 **CLI Documentation →**](docs/cli.md)
- **🚀 High-Performance Backends**: Automatic selection of Rust, `fd`, or Python for the best performance.
- **📊 Rich Directory Analysis**: Get detailed statistics on file counts, extensions, sizes, and more.
- **🔍 Smart File Search**: Use regex and glob patterns to find files with `FdFinder`.
- **🏗️ Architectural Clarity**: High-level visual flows for discovery and processing. [📖 **Architecture Documentation →**](docs/architecture.md)
- **📈 DataFrame Integration**: Convert scan results to [Polars](https://github.com/pola-rs/polars) (or [pandas](https://github.com/pandas-dev/pandas)) DataFrames for powerful analysis.
- **🖼️ File/Image Profiling**: Extract metadata and statistics from various file formats.

  
## Feature Highlights
Quick, copyable examples showing filoma's standout capabilities and where to learn more.

- **Automatic multi-backend scanning:** filoma picks the fastest available backend (Rust → `fd` → pure Python). You can also force a backend for reproducibility. See the backends docs: `docs/backends.md`.

```python
import filoma as flm

# filoma will pick Rust > fd > Python depending on availability
analysis = flm.probe('.')
analysis.print_summary()  # Pretty Rich table output
```

- **Polars-first DataFrame wrapper & enrichment:** Returns a `filoma.DataFrame` (Polars) with helpers to add path components, depth, and file stats for immediate analysis. Docs: `docs/dataframe.md`.

```python
df = flm.probe_to_df('.', enrich=True)  # returns a filoma.DataFrame
print(df.head(2))
```

<details>
<summary><b>📊 See Enriched DataFrame Output</b></summary>

```text
filoma.DataFrame with 2 rows
shape: (2, 18)
┌────────────────┬───────┬────────┬──────────┬───┬─────────┬───────┬────────┬────────┐
│ path           ┆ depth ┆ parent ┆ name     ┆ … ┆ inode   ┆ nlink ┆ sha256 ┆ xattrs │
│ ---            ┆ ---   ┆ ---    ┆ ---      ┆   ┆ ---     ┆ ---   ┆ ---    ┆ ---    │
│ str            ┆ i64   ┆ str    ┆ str      ┆   ┆ i64     ┆ i64   ┆ str    ┆ str    │
╞════════════════╪═══════╪════════╪══════════╪═══╪═════════╪═══════╪════════╪════════╡
│ src/filoma.py  ┆ 1     ┆ src    ┆ filo.py  ┆ … ┆ 1465688 ┆ 1     ┆ null   ┆ {}     │
│ src/core/      ┆ 1     ┆ src    ┆ core     ┆ … ┆ 714364  ┆ 15    ┆ null   ┆ {}     │
└────────────────┴───────┴────────┴──────────┴───┴─────────┴───────┴────────┴────────┘

✨ Enriched columns added: parent, name, stem, suffix, size_bytes, modified_time, 
   created_time, is_file, is_dir, owner, group, mode_str, inode, nlink, sha256, xattrs, depth
```
</details>

- **Ultra-fast discovery with `fd`:** When `fd` is available filoma uses it for very fast file discovery. Advanced usage and patterns: `docs/advanced-usage.md`.

```python
from filoma.directories.fd_finder import FdFinder

finder = FdFinder()
if finder.is_available():
    files = finder.find_files(pattern=r"\.py$", path='src', max_depth=3)
    print(len(files), 'python files found')
```

- **Lightweight, lazy top-level API:** Importing `filoma` is cheap; heavy dependencies load only when used. Quickstart and one-line helpers: `docs/quickstart.md`.

```python
info = flm.probe_file('README.md')
df = flm.probe_to_df('.')
```

- **Seamless Pandas & Polars integration:** `filoma.DataFrame` wraps a Polars DataFrame but provides instant access to pandas.

```python
df = flm.probe_to_df('.')
pd_df = df.pandas  # Instant conversion to pandas
# or set it globally
flm.set_default_dataframe_backend('pandas')
df.native  # returns pandas.DataFrame
```

## Installation

Install `filoma` using `uv` or `pip`:
```bash
pip install filoma
```
```bash
uv pip install filoma
# or 'uv add filoma' to add it to your dependencies)
```

---

## Workflow Demo

This guide follows a typical `filoma` workflow, from basic file profiling to creating dataframes for exploration.

### 1. Profile a Single File

Start by inspecting a single file. `filoma` provides a detailed dataclass with metadata.

```python
import filoma as flm

# Profile a file
file_info = flm.probe_file("README.md")
print(file_info)
```

<details>
<summary><b>📄 See File Metadata Output</b></summary>

```text
Filo(
    path=PosixPath('README.md'), 
    size=6683, 
    mode_str='-rw-r--r--', 
    owner='user', 
    modified=datetime.datetime(2025, 12, 30, 12, 59, 19), 
    is_file=True, 
    ...
)
```
</details>

For images, `probe_image` gives you additional details like shape and pixel statistics.

```python
# Profile an image
img_info = flm.probe_image("docs/assets/images/logo.png")
print(img_info)
```

<details>
<summary><b>🖼️ See Image Analysis Output</b></summary>

```text
ImageReport(
    path='docs/assets/images/logo.png', 
    file_type='png', 
    shape=(462, 433, 4), 
    mean=182.47, 
    unique=145, 
    ...
)
```
</details>

### 2. Analyze a Directory

Scan an entire directory to get a high-level overview.

```python
# Analyze the current directory
analysis = flm.probe('.')

# Print a beautiful summary table
analysis.print_summary()
```

<details open>
<summary><b>📂 See Directory Summary Table</b></summary>

```text
 Directory Analysis: /project
           (🦀 Rust (Parallel)) - 0.50s
┏━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━┓
┃ Metric                   ┃ Value                ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━┩
│ Total Files              │ 27,901               │
│ Total Folders            │ 1,761                │
│ Total Size               │ 596.21 MB            │
│ Average Files per Folder │ 15.84                │
│ Maximum Depth            │ 14                   │
│ Empty Folders            │ 14                   │
│ Analysis Time            │ 0.50s                │
│ Processing Speed         │ 59,167 items/sec     │
└──────────────────────────┴──────────────────────┘
```
</details>

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

print(df_enriched.head(2))
```

### 5. Seamless Pandas Integration

While `filoma` uses Polars internally for speed, converting to pandas is just one property away.

```python
# Convert to a standard pandas DataFrame
pd_df = df_enriched.pandas

print(type(pd_df))
# <class 'pandas.core.frame.DataFrame'>
```

<details>
<summary><b>✨ See Enriched DataFrame Features</b></summary>

Enrichment adds several groups of columns to your path data:

1.  **Path Components**: `parent`, `name`, `stem`, `suffix`
2.  **File Statistics**: `size_bytes`, `modified_time`, `created_time`, `is_file`, `is_dir`, `owner`, `group`, `mode_str`, `inode`, `nlink`, `sha256`, `xattrs`
3.  **Hierarchy**: `depth` (relative nesting level)

```text
filoma.DataFrame with 2 rows
shape: (2, 18)
┌────────────────┬───────┬────────┬──────────┬───┬─────────┬───────┬────────┬────────┐
│ path           ┆ depth ┆ parent ┆ name     ┆ … ┆ inode   ┆ nlink ┆ sha256 ┆ xattrs │
│ ---            ┆ ---   ┆ ---    ┆ ---      ┆   ┆ ---     ┆ ---   ┆ ---    ┆ ---    │
│ str            ┆ i64   ┆ str    ┆ str      ┆   ┆ i64     ┆ i64   ┆ str    ┆ str    │
╞════════════════╪═══════╪════════╪══════════╪═══╪═════════╪═══════╪════════╪════════╡
│ src/filoma.py  ┆ 1     ┆ src    ┆ filo.py  ┆ … ┆ 1465688 ┆ 1     ┆ null   ┆ {}     │
│ src/core/      ┆ 1     ┆ src    ┆ core     ┆ … ┆ 714364  ┆ 15    ┆ null   ┆ {}     │
└────────────────┴───────┴────────┴──────────┴───┴─────────┴───────┴────────┴────────┘
```
</details>

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

**filoma** - Fast, multi-backend file/directory profiling and data preparation.
