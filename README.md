<p align="center">
    <img src="docs/assets/images/logo.png" alt="filoma logo" width="260">
</p>

<p align="center">
    <a href="https://pypi.python.org/pypi/filoma"><img src="https://img.shields.io/pypi/v/filoma.svg" alt="PyPI version"></a>
    <a href="https://pypi.python.org/pypi/filoma"><img src="https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue" alt="Python versions"></a>
    <a href="https://github.com/kalfasyan/filoma/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-CC--BY--4.0-lightgrey" alt="License"></a>
    <a href="https://github.com/astral-sh/ruff"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json" alt="Ruff"></a>
    <a href="https://github.com/kalfasyan/filoma/actions/workflows/ci.yml"><img src="https://github.com/kalfasyan/filoma/actions/workflows/ci.yml/badge.svg" alt="Actions status"></a>
    <a href="https://filoma.readthedocs.io/en/latest/"><img src="https://readthedocs.org/projects/filoma/badge/?version=latest" alt="Documentation Status"></a>
</p>

<p align="center">
  <strong>Fast, multi-backend file/directory profiling and data preparation.</strong>
</p>

<p align="center">
  <code>pip install filoma</code>
</p>

<p align="center">
  <code>import filoma as flm</code>
</p>

<p align="center">
  <a href="docs/installation.md">Installation</a> •
  <a href="https://filoma.readthedocs.io/en/latest/">Documentation</a> •
  <a href="docs/cli.md">Interactive CLI</a> •
  <a href="docs/quickstart.md">Quickstart</a> •
  <a href="docs/cookbook.md">Cookbook</a> •
  <a href="https://github.com/kalfasyan/filoma/blob/main/notebooks/roboflow_demo.ipynb">Roboflow Dataset Demo</a> •
  <a href="https://github.com/kalfasyan/filoma">Source Code</a>
</p>

> 📖 **New to Filoma?** Check out the [**Cookbook**](docs/cookbook.md) for practical, copy-paste recipes for common tasks!
---

`filoma` helps you analyze file directory trees, inspect file metadata, and prepare your data for exploration. It can achieve this blazingly fast using the best available backend (Rust, [`fd`](https://github.com/sharkdp/fd), or pure Python) ⚡🍃
<p align="center">
    <img src="docs/assets/images/filoma_ad.png" alt="Filoma Package Overview" width="400">
</p>

## Key Features
- **🚀 High-Performance Backends**: Automatic selection of Rust, `fd`, or Python for the best performance.
- **📈 DataFrame Integration**: Convert scan results to [Polars](https://github.com/pola-rs/polars) (or [pandas](https://github.com/pandas-dev/pandas)) DataFrames for powerful analysis.
- **📊 Rich Directory Analysis**: Get detailed statistics on file counts, extensions, sizes, and more.
- **🔍 Smart File Search**: Use regex and glob patterns to find files with `FdFinder`.
- **🖼️ File/Image Profiling**: Extract metadata and statistics from various file formats.
- **🏗️ Architectural Clarity**: High-level visual flows for discovery and processing. [📖 **Architecture Documentation →**](docs/architecture.md)
- **🖥️ Interactive CLI**: Beautiful terminal interface for filesystem exploration and DataFrame analysis [📖 **CLI Documentation →**](docs/cli.md)

<p align="center">
    <img src="docs/assets/images/filoma_graph.jpg" alt="Filoma Package Overview" width="800">
</p>

---

## ⚡ Quick Start

`filoma` provides a unified API for all your filesystem analysis needs. Whether you're inspecting a single file or a million-file directory, it stays fast and intuitive.

### 1. Simple File & Image Profiling
Extract rich metadata and statistics from any file or image with a single call.

```python
import filoma as flm

# Profile any file
info = flm.probe_file("README.md")
print(info)
```

<details>
<summary><b>📄 See Metadata Output</b></summary>

```text
Filo(
    path=PosixPath('README.md'), 
    size=12237, 
    mode_str='-rw-rw-r--', 
    owner='user', 
    modified=datetime.datetime(2025, 12, 30, 22, 45, 53), 
    is_file=True,
    ...
)
```
</details>

For images, `probe_image` automatically extracts shapes, types, and pixel statistics.

### 2. Blazingly Fast Directory Analysis
Scan entire directory trees in milliseconds. `filoma` automatically picks the fastest available backend (Rust → `fd` → Python).

```python
# Analyze a directory
analysis = flm.probe('.')

# Print a high-level summary
analysis.print_summary()
```

<details open>
<summary><b>📂 See Directory Summary Table</b></summary>

```text
 Directory Analysis: /project (🦀 Rust (Parallel)) - 0.60s
┏━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━┓
┃ Metric                   ┃ Value                ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━┩
│ Total Files              │ 57,225               │
│ Total Folders            │ 3,427                │
│ Total Size               │ 2,084.90 MB          │
│ Average Files per Folder │ 16.70                │
│ Maximum Depth            │ 14                   │
│ Empty Folders            │ 103                  │
│ Analysis Time            │ 0.60s                │
│ Processing Speed         │ 102,114 items/sec    │
└──────────────────────────┴──────────────────────┘
```
</details>

```python
# Or get a detailed report with extensions and folder stats
analysis.print_report()
```

<details>
<summary><b>📊 See Detailed Directory Report</b></summary>

```text
          File Extensions
┏━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━┓
┃ Extension  ┃ Count  ┃ Percentage ┃
┡━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━┩
│ .py        │ 240    │ 12.8%      │
│ .jpg       │ 1,204  │ 64.2%      │
│ .json      │ 431    │ 23.0%      │
│ .svg       │ 28,674 │ 50.1%      │
└────────────┴────────┴────────────┘

          Common Folder Names
┏━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━┓
┃ Folder Name   ┃ Occurrences ┃
┡━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━┩
│ src           │ 1           │
│ tests         │ 1           │
│ docs          │ 1           │
│ notebooks     │ 1           │
└───────────────┴─────────────┘

          Empty Folders (3 found)
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Path                                       ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ /project/data/raw/empty_set_A              │
│ /project/logs/old/unused                   │
│ /project/temp/scratch                      │
└────────────────────────────────────────────┘
```
</details>

### 3. DataFrames & Enrichment
Convert scan results to Polars DataFrames for advanced analysis. Use `.enrich()` to instantly add path components, file stats, and hierarchy data.

```python
# Scan and get an enriched filoma.DataFrame (Polars)
df = flm.probe_to_df('src', enrich=True)

print(df.head(2))
```

<details open>
<summary><b>📊 See Enriched DataFrame Output</b></summary>

```text
filoma.DataFrame with 2 rows
shape: (2, 18)
┌───────────────────┬───────┬────────┬───────────────┬───┬─────────┬───────┬────────┬────────┐
│ path              ┆ depth ┆ parent ┆ name          ┆ … ┆ inode   ┆ nlink ┆ sha256 ┆ xattrs │
│ ---               ┆ ---   ┆ ---    ┆ ---           ┆   ┆ ---     ┆ ---   ┆ ---    ┆ ---    │
│ str               ┆ i64   ┆ str    ┆ str           ┆   ┆ i64     ┆ i64   ┆ str    ┆ str    │
╞═══════════════════╪═══════╪════════╪═══════════════╪═══╪═════════╪═══════╪════════╪════════╡
│ src/async_scan.rs ┆ 1     ┆ src    ┆ async_scan.rs ┆ … ┆ 7601121 ┆ 1     ┆ null   ┆ {}     │
│ src/filoma        ┆ 1     ┆ src    ┆ filoma        ┆ … ┆ 7603126 ┆ 8     ┆ null   ┆ {}     │
└───────────────────┴───────┴────────┴───────────────┴───┴─────────┴───────┴────────┴────────┘

✨ Enriched columns added: parent, name, stem, suffix, size_bytes, modified_time, 
   created_time, is_file, is_dir, owner, group, mode_str, inode, nlink, sha256, xattrs, depth
```
</details>

- **Seamless Pandas Integration**: Just use `df.pandas` for instant conversion.
- **Lazy Loading**: `import filoma` is cheap; heavy dependencies load only when needed.

### 4. Specialized DataFrame Operations
Filoma's `DataFrame` extends Polars with specialized filesystem operations, providing quick ways to filter and summarize your data.

```python
# Filter by extensions
df.filter_by_extension([".py", ".rs"])

# Quick frequency analysis (counts)
df.extension_counts()
df.directory_counts()
```

<details>
<summary><b>🔍 See Operation Examples</b></summary>

**`filter_by_extension([".py", ".rs"])`**
```text
shape: (3, 1)
┌─────────────────────┐
│ path                │
│ ---                 │
│ str                 │
╞═════════════════════╡
│ src/async_scan.rs   │
│ src/lib.rs          │
│ src/filoma/dedup.py │
└─────────────────────┘
```

**`extension_counts()`**
*Groups files by extension and returns counts.*
```text
shape: (3, 2)
┌────────────┬─────┐
│ extension  ┆ len │
│ ---        ┆ --- │
│ str        ┆ u32 │
╞════════════╪═════╡
│ .py        ┆ 240 │
│ .jpg       ┆ 124 │
│ .json      ┆ 43  │
└────────────┴─────┘
```

**`directory_counts()`**
*Summarizes file distribution across parent directories.*
```text
shape: (3, 2)
┌────────────┬─────┐
│ parent_dir ┆ len │
│ ---        ┆ --- │
│ str        ┆ u32 │
╞════════════╪═════╡
│ src/filoma ┆ 12  │
│ tests      ┆ 8   │
│ docs       ┆ 5   │
└────────────┴─────┘
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
