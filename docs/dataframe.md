# DataFrame Workflow

Get a Polars DataFrame directly:
```python
from filoma import probe_to_df
pl_df = probe_to_df('.')
print(pl_df.head())
```

Wrap existing analysis:
```python
from filoma import probe
analysis = probe('.')
# Prefer using probe_to_df() to get a DataFrame in one step. If you already
# have an analysis object, request a DataFrame explicitly when probing:
#
#   from filoma import probe_to_df
#   pl_df = probe_to_df('.')
#
# Or re-run probing with DataFrame building enabled:
analysis = probe('.', build_dataframe=True)
wrapper = analysis.to_df()
pl_df = wrapper.df
```

Enrichment helpers (chainable):
```python
from filoma import probe_to_df
pl_df = probe_to_df('.', enrich=True)  # depth, path parts, file stats
```

Manual enrichment:
```python
from filoma import probe_to_df
pl_df = probe_to_df('.', enrich=False)
from filoma.dataframe import DataFrame
wrapper = DataFrame(pl_df)
wrapper = wrapper.add_depth_col().add_path_components().add_file_stats_cols()
```

Filtering & grouping:
```python
wrapper.filter_by_extension('.py')
wrapper.group_by_extension()
wrapper.group_by_directory()
```

Export:
```python
wrapper.save_csv('files.csv')
wrapper.save_parquet('files.parquet')
```

Convert to pandas:
```python
pandas_df = probe_to_df('.', to_pandas=True)
```

Tips:
- Use `.add_file_stats_cols()` sparingly on huge trees (it touches filesystem for each path).
- Combine with Polars expressions for advanced analysis.
