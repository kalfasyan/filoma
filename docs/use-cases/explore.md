# Explore a Dataset

You've just been handed a folder — maybe 50 GB of images and CSVs, maybe something you downloaded, maybe a colleague's USB drive. You have no idea what's in it. This page shows you how to explore it with filoma in under a minute.

## The "what's in this folder?" workflow

```python
import filoma as flm

# 1. Quick scan — what's in here?
analysis = flm.probe("./mystery_folder")
analysis.print_summary()
```

This prints a Rich table with file counts, total size, top extensions, and folder structure. It uses the fastest available backend (Rust > fd > Python fallback).

## Get a DataFrame

For filtering, sorting, and export, convert to a Polars DataFrame:

```python
dfw = flm.probe_to_df("./mystery_folder", enrich=True)
print(dfw.head())
```

`enrich=True` adds columns for file depth, path components (parent, stem, suffix), and file stats (size, modification time). Only files are included by default — use `include_dirs=True` to include directories.

## Filter and slice

```python
# Only Python files
py_files = dfw.filter_by_extension(".py")

# Find large files (> 100 MB)
import polars as pl
large = dfw.df.filter(pl.col("size") > 100_000_000)

# Top 10 largest files
dfw.df.sort("size", descending=True).head(10)

# Count by extension
print(dfw.extension_counts())
```

## Drill deeper

### Profile a single file

```python
filo = flm.probe_file("./mystery_folder/report.pdf")
print(filo.size, filo.mime_type, filo.modified)
```

### Profile an image

```python
img = flm.probe_image("./mystery_folder/photo.jpg")
print(img.width, img.height, img.format, img.mode)
```

### Manual enrichment (if you skipped `enrich=True`)

```python
from filoma.dataframe import DataFrame

dfw = DataFrame(dfw.df)
dfw = dfw.add_depth_col().add_path_components().add_file_stats_cols()
```

## Export your findings

```python
# Export to CSV for sharing
dfw.save_csv("mystery_folder_inventory.csv")

# Export to Parquet for later analysis
dfw.save_parquet("mystery_folder_inventory.parquet")

# Convert to pandas
pandas_df = dfw.to_pandas()
```

## Realistic workflow example

Here's a typical exploration session on an unknown directory:

```python
import filoma as flm

path = "./incoming_data"

# 1. What's in here at all?
flm.probe(path).print_summary()

# 2. Get a DataFrame and enrich it
dfw = flm.probe_to_df(path, enrich=True)

# 3. What file types dominate?
print(dfw.extension_counts().head(10))

# 4. Any suspiciously small files?
tiny = dfw.df.filter(pl.col("size") < 100)
print(f"Found {len(tiny)} files under 100 bytes")

# 5. Deepest nesting?
deepest = dfw.df.select(pl.col("depth").max()).item()
print(f"Deepest file is {deepest} levels deep")

# 6. Save for later
dfw.save_parquet("inventory.parquet")
```

## What to read next

- [Directory Scanning guide](../guides/scanning.md) — backend selection, flags, performance tuning
- [DataFrame Workflow guide](../guides/dataframe.md) — enrichment helpers, pandas interop, caching
- [Audit a Dataset](audit.md) — when you're ready to go from exploration to quality checks
- [Deduplicate a Dataset](dedup.md) — find and handle duplicate files
