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
  <strong>Dataset CI for ML — go from a folder to a verified, deduplicated dataset and <em>talk to it</em>, in one pipeline.</strong>
</p>

<p align="center">
  <em>Fast, multi-backend file/directory profiling and data preparation, with a local-first agentic interface.</em>
</p>

<p align="center">
  <code>uv add filoma</code>&nbsp;&nbsp;·&nbsp;&nbsp;<code>pip install filoma</code>
</p>

<p align="center">
  <a href="docs/getting-started/installation.md">Installation</a> •
  <a href="https://filoma.readthedocs.io/en/latest/">Documentation</a> •
  <a href="docs/roadmap/adoption.md">Roadmap</a> •
  <a href="docs/guides/filaraki.md">Agentic Analysis</a> •
  <a href="docs/guides/cli.md">Interactive CLI</a> •
  <a href="docs/getting-started/quickstart.md">Quickstart</a> •
  <a href="docs/tutorials/cookbook.md">Cookbook</a> •
  <a href="https://github.com/kalfasyan/filoma/blob/main/notebooks/roboflow_demo.ipynb">Roboflow Demo</a> •
  <a href="https://github.com/kalfasyan/filoma">Source Code</a>
</p>

> 📖 **New to Filoma?** Check out the [**Cookbook**](docs/tutorials/cookbook.md) for practical, copy-paste recipes for common tasks!

---

`filoma` helps you analyze file directory trees, inspect file metadata, and prepare your data for exploration. It can achieve this blazingly fast using the best available backend (Rust, [`fd`](https://github.com/sharkdp/fd), or pure Python) ⚡🍃

Whether you're auditing a machine-learning dataset, tracking down duplicates across terabytes, or just need a quick overview of what's in a directory — Filoma gives you the tools to go from raw folder structure to actionable insight in seconds.

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
- **🧠 Agentic Analysis**: Natural language interface for file discovery, deduplication, and metadata inspection. [📖 **Filaraki Guide →**](docs/guides/filaraki.md)
- **🖥️ Interactive CLI**: Beautiful terminal interface for filesystem exploration and DataFrame analysis. [📖 **CLI Documentation →**](docs/guides/cli.md)
- **🌐 MCP Server**: Expose all 21 filesystem tools to any MCP-compatible AI assistant ([nanobot](https://github.com/HKUDS/nanobot) recommended). [📖 **MCP Configuration →**](docs/guides/filaraki.md#mcp-server-configuration)

> **🍃 Talk to your filesystem:** `filoma filaraki chat` — ask questions about your data in plain English. Find duplicates, audit datasets, export HTML reports — all from one conversation. [Try it →](docs/guides/filaraki.md)
>
> **🎯 Local AI in 10 seconds:** `curl -sL https://raw.githubusercontent.com/kalfasyan/filoma/main/scripts/install.sh | sh` → Use with [nanobot](https://github.com/HKUDS/nanobot) + [Ollama](https://ollama.com) for fully local filesystem analysis. [Learn more →](docs/guides/filaraki.md#nanobot--ollama-setup)

<p align="center">
    <img src="docs/assets/images/filoma_graph.jpg" alt="Filoma Package Overview" width="800">
</p>

---

## 🛠️ Setup

`filoma` is one command away — no compilers, no API keys, no extra
services required for the core workflow.

```bash
uv add filoma          # recommended — drops it into your project
pip install filoma     # classic pip works too
```

That's it. To see the full pipeline run end-to-end against a tiny
built-in fixture (no download, no flags), run:

```bash
filoma demo
```

It generates a synthetic dataset, runs `scan → enrich → verify → dedup`,
writes a self-contained HTML audit report, and opens it in your browser.

### Optional add-ons (all opt-in)

| Add-on | When you want it | How |
| --- | --- | --- |
| [`fd`](https://github.com/sharkdp/fd) binary | Faster scans on huge trees | `apt install fd-find` / `brew install fd` |
| Rust backend | Maximum scan speed | Pre-built wheels on PyPI; rebuild from source if missing |
| [Ollama](https://ollama.com) | Local `flm.ask(...)` / `filoma filaraki chat` | `curl -fsSL https://ollama.com/install.sh \| sh` |
| Hosted LLM | Cloud-hosted Filaraki | Set `MISTRAL_API_KEY` / `GEMINI_API_KEY` / `OPENAI_API_KEY` |

> 🤖 **Configuring the AI provider?** Don't hand-edit `.env`. Run the
> interactive wizard — it picks the provider, prompts for an API key
> (silent input), and writes a clean `.env` for you:
>
> ```bash
> bash scripts/setup_env.sh
> ```
>
> Supports Ollama (local), Mistral, Gemini, OpenAI, OpenRouter, and any
> OpenAI-compatible endpoint. The `.env` is auto-loaded — no `--env-file`
> or shell exports needed.

See [Installation](docs/getting-started/installation.md) for the full
backend matrix and troubleshooting tips.

---

## ⚡ Quick Start

`filoma` provides a unified API for filesystem analysis.

### End-to-End Example: Folder → DataFrame → Insights

The headline workflow is one fluent line: scan, enrich, verify, and produce
a self-contained HTML audit report. Point it at *any* folder you have —
this snippet uses your current directory so you can run it as-is.

```python
import filoma as flm

# One-line dataset CI: scan → enrich → integrity check → HTML audit report.
# Replace "." with any folder you want to inspect.
pipeline = flm.Pipeline(".").scan().enrich().verify().report()

print(pipeline.report_path)                       # → /tmp/<folder>_audit.html
print("matched:", len(pipeline.verification["matched"]))
print("rows:   ", pipeline.dataframe.df.height)
```

> 💡 **Don't have a sample folder handy?** `filoma demo` ships its own
> tiny synthetic dataset and runs the same pipeline — no Python required.

Need to ask questions in plain English instead? `flm.ask("…")` auto-spins
up a Filaraki agent rooted at your current directory (requires Ollama
running, or any of the supported API keys — see Setup above):

```python
flm.ask("how many python files are here, and what's the largest?").output
```

#### Long form: same pipeline, exposed stage by stage

```python
import filoma as flm

dataset = "."  # swap for any folder you'd like to profile

# 1) Fast scan + high-level summary
analysis = flm.probe(dataset)
analysis.print_summary()

# 2) Build an enriched dataframe (paths, extension, sizes, ownership, timestamps, etc.)
df = flm.probe_to_df(dataset, enrich=True)

# 3) Narrow to a file type and inspect distribution
py_files = df.filter_by_extension(["py"])
print(py_files.extension_counts())
print(py_files.directory_counts().head(3))

# 4) Get the largest files quickly
largest = py_files.sort("size_bytes", descending=True).head(5)
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

Convert scan results to Polars DataFrames with filesystem-specific operations for filtering, grouping, and summarization.

```python
# Scan and get an enriched filoma.DataFrame (Polars)
df = flm.probe_to_df('src', enrich=True)

# Filter and analyze
df.filter_by_extension([".py", ".rs"])
df.extension_counts()
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

✨ Enriched columns: parent, name, stem, suffix, size_bytes, modified_time,
   created_time, is_file, is_dir, owner, group, mode_str, inode, nlink, sha256, xattrs, depth
```

</details>

<details>
<summary><b>🔍 See Operation Examples</b></summary>

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

- **Seamless Pandas Integration**: Just use `df.pandas` for instant conversion.
- **Lazy Loading**: `import filoma` is cheap; heavy dependencies load only when needed.

---

## 🗂️ Advanced Topics

### Dataset Convenience Class

Use the `Dataset` class for orchestration of snapshotting, profiling, integrity checks, and AI interactions:

```python
import filoma as flm

ds = flm.Dataset("./my_data")

# Snapshot, Quality Scan, and Deduplication
ds.snap(mode="deep")
verifier = ds.run_quality_scan()
verifier.print_summary()
dupes = ds.dedup()
print(dupes)  # {"exact": [...], "text": [...], "image": [...]}

# Get an enriched DataFrame of the dataset
df = ds.to_dataframe()
print(df.extension_counts())

# Agentic interaction with this specific dataset
result = await ds.get_filaraki().arun("Is there any class imbalance in my dataset?")
print(result.output)
# Or use the synchronous version (works in Jupyter, IPython, or regular scripts):
# result = ds.get_filaraki().run("Is there any class imbalance in my dataset?")
# print(result.output)
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

## 🍃 Agentic Analysis

Filaraki ("little leaf" / "little buddy" in Greek) is Filoma's agentic interface for natural language filesystem analysis. Available as an interactive chat CLI, programmatic API, or MCP server.

<p align="center">
    <img src="docs/assets/images/filaraki.png" alt="Filaraki Chat Interface" width="400">
</p>

### Interactive Chat CLI

The fastest way to get started is with the **setup wizard**, which configures your AI provider and writes a `.env` file:

```bash
bash scripts/setup_env.sh
```

Then start chatting:

```bash
filoma filaraki chat
```

> 💡 The `.env` file is automatically loaded — no need for `--env-file` or `export` commands.

### Programmatic Usage

```python
from filoma.filaraki import get_agent

agent = get_agent()
result = agent.run("Create a dataframe from notebooks/Weeds-3 with enrichment")
print(result.output)
result = agent.run("Filter by extension: jpg, png")
print(result.output)
result = agent.run("Sort dataframe by size descending and show top 5")
print(result.output)
```

### AI Service Options

Filaraki supports multiple providers — pick whatever fits your setup:

| Provider                             | Requires                                      | Privacy       |
| ------------------------------------ | --------------------------------------------- | ------------- |
| **Ollama** (default)                 | `ollama serve` on `localhost:11434`           | 🔒 100% local |
| **Mistral AI**                       | `MISTRAL_API_KEY`                             | Cloud         |
| **Google Gemini**                    | `GEMINI_API_KEY`                              | Cloud         |
| **OpenAI / OpenRouter / compatible** | `FILOMA_FILARAKI_BASE_URL` + `OPENAI_API_KEY` | Cloud         |

> 🎯 **Quick setup:** Run `bash scripts/setup_env.sh` to configure any provider interactively.

[📖 Full AI configuration guide →](docs/guides/filaraki.md#ai-model-configuration)

### 🏠 Local AI Setup (Nanobot + Ollama)

Run Filoma Filaraki **completely offline** with local models via the MCP server:

```bash
curl -sL https://raw.githubusercontent.com/kalfasyan/filoma/main/scripts/install.sh | sh
```

This installs [nanobot](https://github.com/HKUDS/nanobot) + [Ollama](https://ollama.com) with Filoma's 21 filesystem tools. No API keys, no cloud — everything stays on your machine.

[📖 Full MCP Configuration Guide →](docs/guides/filaraki.md#mcp-server-configuration-with-nanobot)

### 📊 One-Command Audit with HTML Report

Run a **full audit** and export a self-contained **interactive HTML report** in one prompt:

```
filoma filaraki chat
> perform an audit on /path/to/dataset and export an html report called audit.html
```

<details>
<summary><b>📝 What's in the report?</b></summary>

- **Score gauges** for Hygiene and Migration Readiness
- **KPI strip** showing file counts, duplicate groups, and space waste
- **Stage timing bars** (integrity / hygiene / readiness)
- **Priority-tagged Next Actions** — colour-coded high / medium / low
- **Duplicate evidence cards** with exact file paths
- **Collapsible full JSON payload** for deeper inspection

Export formats: `html`, `json`, `md`

</details>

### MCP Server

Expose all 21 filesystem tools to any MCP-compatible client:

```bash
filoma mcp serve
```

[📖 **Browse all guides →**](docs/guides/index.md)

---

## 📊 Performance & Benchmarks

| Backend       | Local SSD (1M files)  | Network (200K files)  |
| ------------- | --------------------- | --------------------- |
| 🦀 **Rust**   | 7.3s — 136K files/sec | 2.3s — 86K files/sec  |
| ⚡ **Async**  | 11.5s — 87K files/sec | 2.8s — 70K files/sec  |
| 🐍 **Python** | 35.5s — 28K files/sec | 15.1s — 13K files/sec |

```bash
python benchmarks/benchmark.py --path /your/directory -n 3 --backend profiling
```

[📖 Full Benchmarks Guide →](docs/reference/benchmarks.md)

---

## License

This work is licensed under a [Creative Commons Attribution 4.0 International License][cc-by].

[![CC BY 4.0][cc-by-image]][cc-by]

[cc-by]: http://creativecommons.org/licenses/by/4.0/
[cc-by-image]: https://i.creativecommons.org/l/by/4.0/88x31.png

---

## Contributing

Contributions welcome! Please check the [issues](https://github.com/kalfasyan/filoma/issues) for planned features and bug reports.
