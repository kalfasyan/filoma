# Cookbook

Practical, copy‑paste recipes for common tasks.

## Top N Largest Files
```python
from filoma import probe_to_df
import polars as pl

# filoma-first: probe_to_df returns a filoma.DataFrame wrapper
dfw = probe_to_df('.')
# If you need the raw polars.DataFrame use `dfw.df` or `dfw.to_polars()`
largest = dfw.df.select(['path','size_bytes']).sort('size_bytes', descending=True).head(10)
print(largest)
```

## Extension Distribution
```python
from filoma import probe_to_df
dfw = probe_to_df('.')
(by_ext := dfw.df.groupby('suffix').count().sort('count', descending=True).head(15))
```

## Count Files per Directory (Depth 1)
```python
from filoma import probe_to_df
dfw = probe_to_df('.')
# add parent using the raw polars DataFrame via `dfw.df`
counts = dfw.df.with_columns(dfw.df['path'].str.split('/').list.slice(-2,1).alias('parent')).groupby('parent').count().sort('count', descending=True)
```

## Filter Only Python Sources
```python
from filoma import probe_to_df
dfw = probe_to_df('.')
# polars-style filter on the underlying DataFrame
py = dfw.df.filter(dfw.df['path'].str.ends_with('.py'))
```

## Add File Metadata Later (Lazy Enrichment)
```python
from filoma import probe_to_df
from filoma.dataframe import DataFrame
# If probe_to_df returns a wrapper, pass its raw polars via .df when needed
base = DataFrame(probe_to_df('.', enrich=False).df)
with_stats = base.add_file_stats_cols()  # adds size, times, owner, etc.
```

## Fast Path Discovery (Skip Metadata)
```python
from filoma.directories import DirectoryProfiler
# Prefer the convenience helper when you want a filoma.DataFrame wrapper:
dfw = probe_to_df('.', enrich=False)

# Or explicitly enable DataFrame building when using DirectoryProfiler:
analysis = DirectoryProfiler(DirectoryProfilerConfig(fast_path_only=True, build_dataframe=True)).probe('.')
paths_df = analysis.to_df().df
```

## Detect Recently Modified Files (last 24h)
```python
from datetime import datetime, timedelta
from filoma import probe_to_df
dfw = probe_to_df('.')
cutoff = datetime.utcnow() - timedelta(hours=24)
# Work on the polars DataFrame via `dfw.df`
recent = dfw.df.filter(dfw.df['modified_time'] > cutoff.isoformat())
```

## Train/Val/Test Split (70/15/15)
```python
from filoma import probe_to_df, ml
dfw = probe_to_df('.')
# preferred: pass the filoma.DataFrame wrapper to ml.split_data
train, val, test = ml.split_data(dfw, train_val_test=(70,15,15), seed=42)
```

## Group Split by Parent Folder
```python
from filoma import probe_to_df, ml
dfw = probe_to_df('.')
train, val, test = ml.split_data(dfw, how='parts', parts=(-2,), seed=42)
```

## Discover Filename Tokens Then Split
```python
from filoma import probe_to_df
from filoma.dataframe import DataFrame
base = DataFrame(probe_to_df('.').df)
# Preferred: use the DataFrame method
df = base.add_filename_features(sep='_')
train, val, test = df.split_data(feature=('feat1',))
```

Use `DataFrame.add_filename_features(...)` to discover filename tokens; it
returns a `filoma.DataFrame` wrapper.

## Export for Downstream Processing
```python
from filoma import probe_to_df
dfw = probe_to_df('.')
# Use wrapper's convenience save methods or raw polars via `dfw.df`
dfw.save_parquet('files.parquet')
dfw.save_csv('files.csv')
```

## Profile Subset (e.g., Only Large Images)
```python
from filoma import probe_to_df, probe_image
import polars as pl
dfw = probe_to_df('.')
images = dfw.df.filter(dfw.df['suffix'].is_in(['.png','.tif','.npy']))
large = images.filter(images['size_bytes'] > 5_000_000)
reports = [probe_image(p) for p in large['path'].to_list()]
```

## Compute SHA256 for Selected Files
```python
from filoma import probe_file
import hashlib
paths = ['README.md','pyproject.toml']
rows = []
for p in paths:
    filo = probe_file(p, compute_hash=True)
    rows.append({'path': filo.path, 'sha256': filo.sha256})
```

## Simple Duplicate Finder (by size then hash)
```python
from filoma import probe_to_df, probe_file
import collections
dfw = probe_to_df('.')
# coarse group by file size (use raw polars via `dfw.df`)
cand = dfw.df.groupby('size_bytes').count().filter(dfw.df['count']>1)['size_bytes'].to_list()
subset = dfw.df.filter(dfw.df['size_bytes'].is_in(cand))
# compute hashes only for candidates
hash_map = collections.defaultdict(list)
for path in subset['path'].to_list():
    filo = probe_file(path, compute_hash=True)
    hash_map[filo.sha256].append(path)
duplicates = [v for v in hash_map.values() if len(v) > 1]
```

## Depth Histogram
```python
from filoma import probe_to_df
dfw = probe_to_df('.')
dfw.df.groupby('depth').count().sort('depth')
```

## Largest Directories by File Count
```python
from filoma import probe_to_df
dfw = probe_to_df('.')
# parent column (quick derivation) using the raw polars DataFrame
parents = dfw.df.with_columns(dfw.df['path'].str.split('/').list.slice(-2,1).alias('parent'))
parents.groupby('parent').count().sort('count', descending=True).head(20)
```

## Smart File Search with FdFinder
The `FdFinder` class provides a powerful way to search for files using regular expressions and glob patterns.

```python
from filoma.directories import FdFinder

finder = FdFinder()

# Find all Python files
python_files = finder.find_files(pattern=r"\.py$")

# Find files by multiple extensions
code_files = finder.find_by_extension(['py', 'rs', 'js'])

# Find files using a glob pattern
config_files = finder.find_files(pattern="*.{json,yaml}", use_glob=True)

print(f"Found {len(python_files)} Python files.")
```

---
Add a recipe request via an issue if something common is missing.
