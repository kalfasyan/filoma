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
- **Automatic speed**: Rust / fd / Python backend selection
- **DataFrame-first**: Direct Polars integration + enrichment helpers
- **One-liners**: `probe`, `probe_to_df`, `probe_file`, `probe_image`
- **Architectural Clarity**: High-level visual flows for discovery and processing
- **Extensible**: Low-level profilers still accessible
- **Interactive CLI**: Beautiful terminal interface for exploration and analysis
- **Agentic Analysis**: Natural language interface for filesystem tasks

## Start here

Best place to begin is the Demo notebook (see the [`Demo` page](tutorials/demo.md) in the docs).

1. Read the [Quickstart](getting-started/quickstart.md)
2. Learn [Core Concepts](guides/concepts.md)
3. Explore the [Architecture & Flow](reference/architecture.md)
4. Explore the [DataFrame Workflow](guides/dataframe.md)
5. Learn about [Filoma Brain](guides/brain.md)
6. Browse recipes in the [Cookbook](tutorials/cookbook.md)
7. Try the [Roboflow Dataset Analysis Demo](tutorials/roboflow_demo.md) (real-world computer vision use case)
8. Dive into the [API Reference](reference/api.md)

## Common Tasks (TL;DR)
| Task | Snippet |
|------|---------|
| Scan dir | `probe('.')` |
| DataFrame | `probe_to_df('.')` |
| Chat with Brain | `filoma brain chat` |
| Largest N files | see Cookbook |
| Filter extension | `df.filter_by_extension('.py')` |
| Add stats | `df.add_file_stats_cols()` |

## Installation
```bash
pip install filoma
```

Want performance? Install Rust (for fastest backend) or fd.

---
Need something else? Check the [Cookbook](tutorials/cookbook.md) or jump to the [API](reference/api.md).
