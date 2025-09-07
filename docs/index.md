# filoma

Fast, multi-backend directory analysis & file/image profiling with a tiny API surface.

```python
from filoma import probe, probe_to_df, probe_file

analysis = probe('.')            # directory summary
analysis.print_summary()

df = probe_to_df('.')            # Polars DataFrame of paths
print(df.head())

filo = probe_file('README.md')   # single file metadata
print(filo.size)
```

## Why filoma?
- **Automatic speed**: Rust / fd / Python backend selection
- **DataFrame-first**: Direct Polars integration + enrichment helpers
- **One-liners**: `probe`, `probe_to_df`, `probe_file`, `probe_image`
- **Deterministic ML splits**: Group-aware, leakage-resistant
- **Extensible**: Low-level profilers still accessible

## Start here
1. Read the [Quickstart](quickstart.md)
2. Learn [Core Concepts](concepts.md)
3. Explore the [DataFrame Workflow](dataframe.md)
4. Browse recipes in the [Cookbook](cookbook.md)
5. Dive into the [API Reference](api.md)

## Common Tasks (TL;DR)
| Task | Snippet |
|------|---------|
| Scan dir | `probe('.')` |
| DataFrame | `probe_to_df('.')` |
| Largest N files | see Cookbook |
| Filter extension | `df.filter_by_extension('.py')` |
| Add stats | `df.add_file_stats_cols()` |
| ML split | `ml.auto_split(df)` |

## Installation (uv)
```bash
uv add filoma
```

Want performance? Install Rust (for fastest backend) or fd.

---
Need something else? Check the [Cookbook](cookbook.md) or jump to the [API](api.md).
