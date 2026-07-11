# filoma

Fast, multi-backend directory analysis & file/image profiling with a tiny API surface.

```python
from filoma import probe, probe_to_df, probe_file

filo = probe_file('README.md')   # single file metadata
print(filo.size)

analysis = probe('.')            # directory summary
analysis.print_summary()         # pretty Rich table output

df = probe_to_df('.')            # filoma.DataFrame wrapper containing a Polars DataFrame of paths
df.add_path_components()         # add columns for e.g. parent, stem, suffix
df.add_file_stats_cols()         # add file stats columns (like size, mtime, etc.)
df.add_depth_col()               # add depth column (file nesting level)
df.add_filename_features()       # instance method: discover filename tokens (see Demo)
```

## Interactive CLI

Prefer a visual interface? Use the interactive CLI for filesystem exploration and data analysis:

```bash
filoma                    # Launch interactive file browser
filoma /path/to/analyze   # Start in specific directory
```

Navigate with arrow keys, probe files and directories, and analyze DataFrames—all with beautiful terminal UI powered by Rich and questionary. [Learn more →](guides/cli.md)

## Why filoma?

- **Dataset CI for ML**: folder → verified dataset → insights → agent, in one pipeline
- **Automatic speed**: Rust / fd / Python backend selection
- **DataFrame-first**: Polars-native wrapper with enrichment helpers
- **Deduplication**: exact + near-duplicate text + near-duplicate images
- **Quality gates**: `filoma-gates.yml` with pass/fail exit codes for CI
- **Agentic interface**: `filoma ask`, interactive chat, MCP server
- **Interactive CLI**: Rich-powered terminal UI for exploration

## Start here

1. Read the [Quickstart](getting-started/quickstart.md) — pick your persona and go
2. See how filoma compares: [Why filoma over X?](getting-started/comparisons.md)
3. Jump to a use case: [Audit](use-cases/audit.md) | [Explore](use-cases/explore.md) | [Dedup](use-cases/dedup.md) | [Talk](use-cases/agent.md)
4. Learn [Core Concepts](guides/concepts.md)
5. Explore the [Architecture & Flow](reference/architecture.md)
6. Browse recipes in the [Cookbook](tutorials/cookbook.md)
7. Dive into the [API Reference](reference/api.md)

## Common Tasks

| Task                | Snippet                                    |
| ------------------- | ------------------------------------------ |
| Audit a dataset     | `filoma audit ./data --export report.html` |
| Scan directory      | `flm.probe('.')`                           |
| Get DataFrame       | `flm.probe_to_df('.')`                     |
| Find duplicates     | `flm.Pipeline('./data').scan().dedup()`    |
| Chat with your data | `filoma ask "what's in this folder?"`      |
| Filter by extension | `dfw.filter_by_extension('.py')`           |
| Add file stats      | `dfw.add_file_stats_cols()`                |

## Installation

```bash
uv add filoma          # recommended
pip install filoma     # classic pip works too
```

Want performance? Install Rust (for fastest backend) or fd.

---

Need something else? Check the [Cookbook](tutorials/cookbook.md) or jump to the [API](reference/api.md).
