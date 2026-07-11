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
  <strong>Dataset CI for ML — folder → verified dataset → insights → agent, in one pipeline.</strong>
</p>

<p align="center">
  <code>uv add filoma</code>&nbsp;&nbsp;·&nbsp;&nbsp;<code>pip install filoma</code>
</p>

<p align="center">
  <a href="https://filoma.readthedocs.io/en/latest/">Documentation</a> •
  <a href="docs/getting-started/quickstart.md">Quickstart</a> •
  <a href="docs/tutorials/cookbook.md">Cookbook</a> •
  <a href="docs/roadmap/adoption.md">Roadmap</a>
</p>

---

`filoma` profiles file trees, builds DataFrames, finds duplicates, runs
integrity checks, and lets you **talk to your filesystem** — all with a
tiny API and automatic backend selection (Rust → fd → Python).

<p align="center">
    <img src="docs/assets/images/filoma_ad.png" alt="Filoma Package Overview" width="400">
</p>

## Show me

```python
import filoma as flm

# One line: scan → enrich → verify → HTML audit report
flm.Pipeline("./data").scan().enrich().verify().report()

# Talk to it
flm.ask("how many corrupted images are in ./data?")

# Watch for drift (designed for CI)
flm.Dataset("./data").snap().verify().check_gates("gates.yml")
```

```bash
# Same from the terminal
filoma audit ./data --export report.html
filoma ask "find duplicates in ./dataset"
filoma watch ./data --snapshot baseline.json --gates gates.yml
```

[Quickstart →](docs/getting-started/quickstart.md) &nbsp; [Cookbook →](docs/tutorials/cookbook.md) &nbsp; [Full docs →](https://filoma.readthedocs.io/en/latest/)

---

## Capabilities

| Area              | What it does                                                    |
| ----------------- | --------------------------------------------------------------- |
| **Scan**          | Directory trees in ms — Rust, fd, or Python                     |
| **DataFrame**     | Polars-native wrapper with enrichment, filter, sort, export     |
| **Dedup**         | Exact, text near-dupes, image near-dupes                        |
| **Integrity**     | Snapshots, manifests, SHA-256 verification                      |
| **Quality gates** | YAML policy (`filoma-gates.yml`), pass/fail for CI              |
| **Agentic**       | 28 tools via chat, `flm.ask()`, MCP server, schema proposals    |
| **RAG search**    | LanceDB vector store — search your files by meaning             |
| **Watch mode**    | Snapshot → drift detect → gates check → JSON export             |
| **Plugins**       | Third-party tools via `filoma.tools` entry points               |
| **Skills**        | Drop-in workflows for Claude Code, Cursor, Copilot, Aider, etc. |

---

## Backends

| Backend    | 1M files (local SSD)  | 200K files (network)  |
| ---------- | --------------------- | --------------------- |
| Rust       | 7.3s — 136K files/sec | 2.3s — 86K files/sec  |
| fd / Async | 11.5s — 87K files/sec | 2.8s — 70K files/sec  |
| Python     | 35.5s — 28K files/sec | 15.1s — 13K files/sec |

Auto-detected at runtime. No config needed.

[Benchmarks →](docs/reference/benchmarks.md)

---

## Guides

| Persona        | Start here                                     |
| -------------- | ---------------------------------------------- |
| ML Engineer    | [Audit a Dataset](docs/use-cases/audit.md)     |
| Data Engineer  | [Explore a Dataset](docs/use-cases/explore.md) |
| Researcher     | [Talk to Your Data](docs/use-cases/agent.md)   |
| DevOps / CI    | [Watch for Drift](docs/guides/cli.md)          |
| Package author | [Plugin Discovery](docs/roadmap/adoption.md)   |

[Installation →](docs/getting-started/installation.md) &nbsp;
[Core Concepts →](docs/guides/concepts.md) &nbsp;
[API Reference →](https://filoma.readthedocs.io/en/latest/reference/api/)

---

## License

Creative Commons Attribution 4.0 International ([CC BY 4.0](http://creativecommons.org/licenses/by/4.0/))

[![CC BY 4.0](https://i.creativecommons.org/l/by/4.0/88x31.png)](http://creativecommons.org/licenses/by/4.0/)
