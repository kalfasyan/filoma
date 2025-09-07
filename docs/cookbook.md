# Cookbook

Practical, copy‑paste recipes for common tasks.

## Top N Largest Files
```python
from filoma import probe_to_df
import polars as pl

pl_df = probe_to_df('.')  # Polars DataFrame
largest = pl_df.select(['path','size_bytes']).sort('size_bytes', descending=True).head(10)
print(largest)
```

## Extension Distribution
```python
from filoma import probe_to_df
pl_df = probe_to_df('.')
(by_ext := pl_df.groupby('suffix').count().sort('count', descending=True).head(15))
```

## Count Files per Directory (Depth 1)
```python
from filoma import probe_to_df
pl_df = probe_to_df('.')
# add parent
pl_df = pl_df.with_columns(pl_df['path'].str.split('/').list.slice(-2,1).alias('parent'))
counts = pl_df.groupby('parent').count().sort('count', descending=True)
```

## Filter Only Python Sources
```python
from filoma import probe_to_df
pl_df = probe_to_df('.')
py = pl_df.filter(pl_df['path'].str.ends_with('.py'))
```

## Add File Metadata Later (Lazy Enrichment)
```python
from filoma import probe_to_df
from filoma.dataframe import DataFrame
base = DataFrame(probe_to_df('.', enrich=False))
with_stats = base.add_file_stats_cols()  # adds size, times, owner, etc.
```

## Fast Path Discovery (Skip Metadata)
```python
from filoma.directories import DirectoryProfiler
# Prefer the convenience helper when you want a Polars DataFrame directly:
pl_df = probe_to_df('.', enrich=False)

# Or explicitly enable DataFrame building when using DirectoryProfiler:
analysis = DirectoryProfiler(fast_path_only=True, build_dataframe=True).probe('.')
paths_df = analysis.to_df().df
```

## Detect Recently Modified Files (last 24h)
```python
from datetime import datetime, timedelta
from filoma import probe_to_df
pl_df = probe_to_df('.')
cutoff = datetime.utcnow() - timedelta(hours=24)
recent = pl_df.filter(pl_df['modified_time'] > cutoff.isoformat())
```

## Train/Val/Test Split (70/15/15)
```python
from filoma import probe_to_df, ml
pl_df = probe_to_df('.')
train, val, test = ml.auto_split(pl_df, train_val_test=(70,15,15), seed=42)
```

## Group Split by Parent Folder
```python
from filoma import probe_to_df, ml
pl_df = probe_to_df('.')
train, val, test = ml.auto_split(pl_df, how='parts', parts=(-2,), seed=42)
```

## Discover Filename Tokens Then Split
```python
from filoma import probe_to_df, ml
pl_df = probe_to_df('.')
pl_df = ml.discover_filename_features(pl_df, sep='_')
train, val, test = ml.auto_split(pl_df, how='tokens')
```

## Export for Downstream Processing
```python
from filoma import probe_to_df
pl_df = probe_to_df('.')
pl_df.write_parquet('files.parquet')
pl_df.write_csv('files.csv')
```

## Profile Subset (e.g., Only Large Images)
```python
from filoma import probe_to_df, probe_image
import polars as pl
pl_df = probe_to_df('.')
images = pl_df.filter(pl_df['suffix'].is_in(['.png','.tif','.npy']))
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
pl_df = probe_to_df('.')
# coarse group by file size
cand = pl_df.groupby('size_bytes').count().filter(pl_df['count']>1)['size_bytes'].to_list()
subset = pl_df.filter(pl_df['size_bytes'].is_in(cand))
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
pl_df = probe_to_df('.')
pl_df.groupby('depth').count().sort('depth')
```

## Largest Directories by File Count
```python
from filoma import probe_to_df
pl_df = probe_to_df('.')
# parent column (quick derivation)
parents = pl_df.with_columns(pl_df['path'].str.split('/').list.slice(-2,1).alias('parent'))
parents.groupby('parent').count().sort('count', descending=True).head(20)
```

---
Add a recipe request via an issue if something common is missing.
