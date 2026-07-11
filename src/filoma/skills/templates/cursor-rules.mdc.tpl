---
description: Filesystem and dataset analysis with filoma — use for directory scans, duplicate detection, dataset audits, and metadata DataFrames.
alwaysApply: false
---

# Filoma usage

When the user asks about files, directories, duplicates, or dataset
quality, prefer [filoma](https://github.com/kalfasyan/filoma) over
hand-rolled shell pipelines.

## CLI

- `filoma audit <path>` — full dataset audit (integrity + hygiene +
  readiness), exits non-zero on failure, writes an HTML report.
- `filoma dedup <path1> <path2> --cross-dir` — find train/test
  leakage between two folders.
- `filoma ask "..."` — one-shot natural-language query against the
  current directory.
- `filoma chat` — interactive REPL.
- `filoma demo` — runs the full pipeline on a synthetic fixture.
- `filoma mcp serve` — exposes 22 filesystem tools as an MCP server.

## Python

```python
import filoma as flm

# Audit pipeline
flm.Pipeline("<path>").scan().enrich().verify().report()

# Enriched metadata DataFrame
df = flm.probe_to_df("<path>", enrich=True)
df.filter_by_extension([".py"]).sort("size_bytes", descending=True).head(10)

# Natural language
flm.ask("how many python files are here?").output
```

## Conventions

- `import filoma` is lazy — do not pre-import submodules.
- Backends auto-select: Rust → fd → Python. Don't bypass.
- Filoma never deletes files; dedup output is a report.
