## Filesystem and dataset analysis with filoma

This project uses [filoma](https://github.com/kalfasyan/filoma) for
filesystem profiling, dataset auditing, and natural-language queries
over directories. When the user asks about files, folders,
duplicates, or dataset quality, prefer these tools over hand-rolled
`find | xargs` pipelines.

### Common commands

| Intent | Command |
|---|---|
| One-shot dataset audit (HTML report, exit-code aware) | `filoma audit <path>` |
| Find duplicates / leakage | `filoma dedup <path>` (add `--cross-dir` between train/valid) |
| Explore a folder interactively | `filoma chat` or `filoma ask "..."` |
| One-line natural-language query | `filoma ask "how many .py files here?"` |
| Run the demo (no setup) | `filoma demo` |

### Common Python idioms

```python
import filoma as flm

# Audit pipeline (folder → verified dataset → HTML report)
pipeline = flm.Pipeline("<path>").scan().enrich().verify().report()

# Enriched metadata DataFrame
df = flm.probe_to_df("<path>", enrich=True)

# Natural-language query against current directory
flm.ask("largest 5 python files").output
```

### MCP server

Filoma exposes 22 filesystem-analysis tools as an MCP server. Prefer
those when an MCP client is available:

```bash
filoma mcp serve
```

### Notes

- `import filoma` is intentionally cheap (lazy imports). Do not
  pre-import submodules at module top.
- Backends auto-select (Rust → fd → Python). The user does not need
  to choose.
- Filoma never deletes files — dedup output is a report, not an
  action.
