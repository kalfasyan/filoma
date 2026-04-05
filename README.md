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
  <a href="docs/getting-started/installation.md">Installation</a> •
  <a href="https://filoma.readthedocs.io/en/latest/">Documentation</a> •
  <a href="docs/guides/brain.md">Agentic Analysis</a> •
  <a href="docs/guides/cli.md">Interactive CLI</a> •
  <a href="docs/getting-started/quickstart.md">Quickstart</a> •
  <a href="docs/tutorials/cookbook.md">Cookbook</a> •
  <a href="https://github.com/kalfasyan/filoma/blob/main/notebooks/roboflow_demo.ipynb">Roboflow Demo</a> •
  <a href="https://github.com/kalfasyan/filoma">Source Code</a>
</p>

> 📖 **New to Filoma?** Check out the [**Cookbook**](docs/tutorials/cookbook.md) for practical, copy-paste recipes for common tasks!

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
- **🛡️ Dataset Integrity & Quality**: Unified integrity checking for snapshots, manifests, and automated quality scans (corruption, duplicates, leakage, class balance). [📖 **Data Integrity Guide →**](docs/guides/data-integrity.md)
- **🧠 Agentic Analysis**: Natural language interface for file discovery, deduplication, and metadata inspection. [📖 **Brain Guide →**](docs/guides/brain.md)
- **🖥️ Interactive CLI**: Beautiful terminal interface for filesystem exploration and DataFrame analysis. [📖 **CLI Documentation →**](docs/guides/cli.md)
- **🌐 MCP Server**: Expose all 21 filesystem tools to any MCP-compatible AI assistant ([nanobot](https://github.com/kniven/nanobot) recommended). [📖 **MCP Configuration →**](docs/guides/brain.md#mcp-server-configuration)

> **🎯 Local AI in 10 seconds:** `curl -sL https://raw.githubusercontent.com/kalfasyan/filoma/main/scripts/install.sh | sh` → Use with [nanobot](https://github.com/kniven/nanobot) + [Ollama](https://ollama.com) for fully local filesystem analysis. [Learn more →](docs/guides/brain.md#nanobot--ollama-setup)

<p align="center">
    <img src="docs/assets/images/filoma_graph.jpg" alt="Filoma Package Overview" width="800">
</p>

---

## ⚡ Quick Start

`filoma` provides a unified API for filesystem analysis.

### End-to-End Example: Folder → DataFrame → Insights

This is the core Filoma workflow in one place: scan a folder, build a rich dataframe, filter it, and extract quick insights.

```python
import filoma as flm

dataset = "notebooks/Weeds-3"

# 1) Fast scan + high-level summary
analysis = flm.probe(dataset)
analysis.print_summary()

# 2) Build an enriched dataframe (paths, extension, sizes, ownership, timestamps, etc.)
df = flm.probe_to_df(dataset, enrich=True)

# 3) Narrow to image files and inspect distribution
images = df.filter_by_extension(["jpg", "png"])
print(images.extension_counts())
print(images.directory_counts().head(3))

# 4) Get the largest files quickly
largest = images.sort("size_bytes", descending=True).head(5)
print(largest.select(["path", "size_bytes"]))
```

This flow is typically the fastest way to move from raw folder structure to actionable dataset insight.

### 1. File & Image Profiling

Extract rich metadata and statistics from any file or image.

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

### 2. Directory Analysis

Scan entire directory trees in milliseconds. `filoma` automatically picks the fastest available backend (Rust → `fd` → Python).

```python
# Analyze a directory
analysis = flm.probe('.')

# Print high-level summary
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

### 3. DataFrame Analysis

Convert scan results to Polars DataFrames for advanced analysis.

```python
# Scan and get an enriched filoma.DataFrame (Polars)
df = flm.probe_to_df('src', enrich=True)

# Perform operations
df.filter_by_extension([".py", ".rs"])
df.directory_counts()
```

<details>
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

Filoma's `DataFrame` extends Polars with filesystem-specific operations for quick filtering and summarization.

```python
# Filter by extensions
df.filter_by_extension([".py", ".rs"])

# Quick frequency analysis
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

**`extension_counts()`** — groups files by extension and returns counts.

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

**`directory_counts()`** — summarizes file distribution across parent directories.

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

---

## 🗂️ Advanced Topics

### Dataset Convenience Class
Use the `Dataset` class for orchestration of snapshotting, profiling, integrity checks, and AI interactions:

```python
import filoma as flm

ds = flm.Dataset("./my_data")

# Snapshot, Quality Scan, and Deduplication
ds.snap(mode="deep")
ds.run_quality_scan()
ds.dedup()

# Get an enriched DataFrame of the dataset
df = ds.to_dataframe()
print(df.extension_counts())

# Agentic interaction with this specific dataset
ds.get_brain().run("Is there any class imbalance in my dataset?")
```

### Dataset Integrity & Quality
Filoma provides a comprehensive suite for dataset validation (corruption, leaks, balance) and manifest integrity:

```python
from filoma.core.verifier import DatasetVerifier
verifier = DatasetVerifier("./data")
verifier.run_all()
verifier.print_summary()
```

### Deduplication
Find duplicate files, images (perceptual hash), or text files.

```bash
# Standard find
filoma dedup /path/to/dataset

# Cross-directory find
filoma dedup train/ valid/ --cross-dir
```

### Agentic Analysis
Connect a "brain" to your filesystem for natural language interaction:

```python
from filoma.brain import get_agent

agent = get_agent()
await agent.run("Create a dataframe from notebooks/Weeds-3 with enrichment")
await agent.run("Filter by extension: jpg, png")
await agent.run("Summarize dataframe and show top directories")
await agent.run("Sort dataframe by size descending and show top 5")
```

Or use the interactive chat CLI:

```bash
filoma brain chat
# Then ask:
# - create a dataframe from notebooks/Weeds-3
# - filter by extension jpg,png
# - summarize dataframe
# - export dataframe to weeds_images.csv
```

#### Advanced Workflow Orchestration
Filoma Brain now includes advanced orchestrator tools for enterprise-grade dataset analysis:

```bash
# Run advanced workflow examples
make brain-advanced

# Or in code:
await agent.run("Run a corrupted file audit on /path/to/dataset")
await agent.run("Generate a dataset hygiene report for /path/to/dataset")
await agent.run("Assess the migration readiness of /path/to/dataset")
```

These tools provide structured, deterministic reports with detailed findings, recommendations, and confidence scores.

### Interactive CLI
```bash
filoma brain chat
```

[📖 **Browse all guides →**](docs/guides/index.md)

---

## 📊 Performance & Benchmarks

Need to compare backend performance? Check out the comprehensive [**Benchmarks Guide**](docs/reference/benchmarks.md)!

**Local SSD** (1M files):
- 🦀 **Rust**: 7.3s (136K files/sec)
- ⚡ **Async**: 11.5s (87K files/sec)
- 🐍 **Python**: 35.5s (28K files/sec)

**Network Storage** (200K files, cold cache):
- 🦀 **Rust**: 2.3s (86K files/sec)
- ⚡ **Async**: 2.8s (70K files/sec)
- 🐍 **Python**: 15.1s (13K files/sec)

```bash
python benchmarks/benchmark.py --path /your/directory -n 3 --backend profiling
```

---

## License

This work is licensed under a [Creative Commons Attribution 4.0 International License][cc-by].

[![CC BY 4.0][cc-by-image]][cc-by]

[cc-by]: http://creativecommons.org/licenses/by/4.0/
[cc-by-image]: https://i.creativecommons.org/l/by/4.0/88x31.png

---

## Contributing

Contributions welcome! Please check the [issues](https://github.com/filoma/filoma/issues) for planned features and bug reports.
