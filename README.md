<p align="center">
  <img src="docs/assets/images/logo.png" alt="filoma logo" width="260">
</p>
<p align="center">
    <em>Dataset CI for ML — folder → verified dataset → insights → agent, in one pipeline.</em>
</p>
<p align="center">
<a href="https://pypi.python.org/pypi/filoma"><img src="https://img.shields.io/pypi/v/filoma.svg" alt="PyPI version"></a>
<a href="https://pypi.python.org/pypi/filoma"><img src="https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue" alt="Python versions"></a>
<a href="https://github.com/kalfasyan/filoma/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-CC--BY--4.0-lightgrey" alt="License"></a>
<a href="https://github.com/astral-sh/ruff"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json" alt="Ruff"></a>
<a href="https://github.com/kalfasyan/filoma/actions/workflows/ci.yml"><img src="https://github.com/kalfasyan/filoma/actions/workflows/ci.yml/badge.svg" alt="Actions status"></a>
<a href="https://filoma.readthedocs.io/en/latest/"><img src="https://readthedocs.org/projects/filoma/badge/?version=latest" alt="Documentation Status"></a>
</p>

---

**Documentation**: [https://filoma.readthedocs.io](https://filoma.readthedocs.io/en/latest/)

**Source Code**: [https://github.com/kalfasyan/filoma](https://github.com/kalfasyan/filoma)

---

**Filoma** profiles file trees, builds DataFrames, finds duplicates, runs integrity checks, and lets you **talk to your filesystem** — all with a tiny API and automatic backend selection (Rust → fd → Python).

The key features are:

- **Fast**: Scans 1M files in 7 seconds with the Rust backend. Auto-detected at runtime — no config needed.
- **DataFrame-native**: Polars-powered wrapper with enrichment, filter, sort, and multi-format export.
- **Dedup**: Exact duplicates, text near-duplicates, and image near-duplicate detection.
- **Integrity**: Snapshots, manifests, and SHA-256 verification for dataset versioning.
- **CI-ready**: YAML quality gates (`filoma-gates.yml`) with pass/fail for your pipelines.
- **Agentic**: 30 filesystem tools via chat, `flm.ask()`, MCP server, and schema proposals.
- **Vector search**: LanceDB-backed RAG — search your files by meaning.
- **Watch mode**: Snapshot → drift detect → gates check → JSON export.
- **Extensible**: Third-party plugins via `filoma.tools` entry points and bundled skill workflows.

---

## Installation

```console
$ pip install filoma

---> 100%
```

or with uv:

```bash
uv add filoma
```

**Note**: The Rust extension (fastest backend) is bundled automatically by `pip`/`uv` above — no separate build step needed. See the [Installation guide](docs/getting-started/installation.md#optimization-optional) if filoma falls back to the fd/Python backend on your platform.

Optional extras:

```bash
pip install "filoma[dedup]"   # near-duplicate detection
pip install "filoma[rag]"     # LanceDB vector search
pip install "filoma[stats]"   # statistical analysis extras
```

---

## Use with GitHub Copilot

The fastest way to try filoma: plug it into GitHub Copilot (VS Code chat, Copilot CLI, or Copilot coding agent) — no Python code required.

**Agent Skill** — teaches Copilot to drive filoma's CLI for you:

```bash
filoma skills install --scope vscode   # writes ./.github/skills/filoma-*/SKILL.md
```

**MCP server** — gives Copilot real, callable tools (`probe_directory`, `audit_dataset`, `search_files`, and more):

```bash
copilot mcp add filoma -- uvx -p 3.11 filoma mcp serve
```

Both work via `uvx` — no `pip install filoma` needed to try them out. See the [Filaraki guide](docs/guides/filaraki.md#using-filoma-with-github-copilot) for VS Code chat setup, nanobot, and other MCP clients.

---

## Example

### Your first scan

```python
import filoma as flm

# Scan a directory — the Rust backend kicks in automatically
analysis = flm.probe("./my-dataset")

# Get a Polars DataFrame, enriched with depth, path components, and file stats
df = flm.probe_to_df("./my-dataset")

# Filter and explore
images = df.filter("mime_type", "image/*")
large = df.filter_size(5, "MB", "gt")
print(df.summary())
```

### Run it

```bash
python -c "import filoma as flm; flm.probe('.').print_summary()"
```

```
📊 Directory Analysis: /home/user/my-dataset
   Total files: 12,847
   Total size: 3.2 GB
   Types: .png (4,201), .json (3,100), .txt (2,546), .jpg (3,000)
```

---

## Example Upgrade

### Audit a dataset (scan → enrich → verify → report)

```python
import filoma as flm

# One fluent pipeline — a single filesystem walk
flm.Pipeline("./data").scan().enrich().verify().report()
```

```bash
filoma audit ./data --export report.html
```

This produces an HTML audit report with file counts, type breakdowns, integrity status, and warnings.

### Talk to your filesystem

```python
import filoma as flm

result = flm.ask("how many corrupted images are in ./dataset?")
print(result.output)
```

```bash
filoma ask "find all python files modified in the last week"
```

### Validate in CI

```python
import filoma as flm

ds = flm.Dataset("./data")
ds.snap().verify().check_gates("gates.yml")
```

```bash
filoma watch ./data --snapshot baseline.json --gates gates.yml
```

Define quality gates in `filoma-gates.yml`:

```yaml
gates:
  - name: "max file count"
    rule: "file_count <= 100000"
  - name: "no corrupt images"
    rule: "corrupt_images == 0"
  - name: "allowed types only"
    rule: 'mime_types in ["image/png", "application/json"]'
```

---

## Backends

Filoma auto-detects the fastest available backend at runtime:

| Backend    | 1M files (local SSD)  | 200K files (network)  |
| ---------- | --------------------- | --------------------- |
| Rust       | 7.3s — 136K files/sec | 2.3s — 86K files/sec  |
| fd / Async | 11.5s — 87K files/sec | 2.8s — 70K files/sec  |
| Python     | 35.5s — 28K files/sec | 15.1s — 13K files/sec |

No configuration required — the fastest backend is selected for you.

---

## Recap

In summary, you get:

- **One-line scans** — `flm.probe(path)` gives you a full directory analysis.
- **Fluent pipelines** — chain `.scan().enrich().verify().report()` with shared state.
- **Agentic queries** — `flm.ask("question")` talks to your filesystem in natural language.
- **DataFrame power** — Polars-native, with enrichment, lineage tracking, and export.
- **CI integration** — Snapshot, verify, and gate-check in any pipeline.
- **Auto backend** — Rust when available, fd as fallback, Python as last resort.

---

## Dependencies

Filoma stands on the shoulders of:

- [Polars](https://pola.rs) for fast DataFrames.
- [Pydantic](https://docs.pydantic.dev) and [pydantic-ai](https://ai.pydantic.dev) for the agentic layer.
- [Rich](https://rich.readthedocs.io) for beautiful terminal output.
- [Typer](https://typer.tiangolo.com) for the CLI.
- Optional Rust core via [Maturin](https://www.maturin.rs) / [PyO3](https://pyo3.rs).

---

## Guides

| Persona        | Start here                                     |
| -------------- | ---------------------------------------------- |
| ML Engineer    | [Audit a Dataset](docs/use-cases/audit.md)     |
| Data Engineer  | [Explore a Dataset](docs/use-cases/explore.md) |
| Researcher     | [Talk to Your Data](docs/use-cases/agent.md)   |
| DevOps / CI    | [Watch for Drift](docs/guides/cli.md)          |
| Package author | [Plugin Discovery](docs/roadmap/adoption.md)   |

---

## License

This project is licensed under the terms of the Creative Commons Attribution 4.0 International ([CC BY 4.0](http://creativecommons.org/licenses/by/4.0/)).
