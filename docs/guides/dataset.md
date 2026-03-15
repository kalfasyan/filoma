# Dataset Management

The `Dataset` class provides a high-level, unified interface for managing filesystem-based datasets. By consolidating profiling, snapshotting, integrity verification, deduplication, and AI-driven analysis, it acts as a central hub for `filoma`'s features.

## Initialization

Initialize the `Dataset` by providing the path to the root directory of your dataset:

```python
import filoma as flm

# Initialize with the root path
ds = flm.Dataset("./path/to/my_dataset")
```

## Workflow Orchestration

The `Dataset` class allows for a fluent API, meaning you can chain operations to build comprehensive workflows.

### 1. Snapshotting
Capture the state of your dataset with configurable integrity checks.

```python
# Create a snapshot with "deep" integrity
ds.snap(mode="deep")
```

### 2. Quality and Integrity
Perform deep content checks, such as corruption detection and file integrity audits.

```python
# Run automatic quality scans
verifier = ds.run_quality_scan()
verifier.print_summary()

# Verify integrity against a snapshot
results = ds.verify(snapshot_path="./manifest.json")
```

### 3. Data Analysis
Convert your dataset into a queryable tabular format.

```python
# Obtain an enriched Polars DataFrame
df = ds.to_dataframe()

# Use standard Filoma/Polars features
print(df.extension_counts())
```

### 4. Deduplication
Find and handle redundant files across your dataset.

```python
# Find duplicate files, images, and text
duplicates = ds.dedup()
```

### 5. Agentic Exploration
Use the `brain` agent to ask natural language questions about your dataset.

```python
# Get insights from the AI assistant
ds.get_brain().run("Analyze the file distribution and identify potential data quality issues.")
```

## Caching
To improve performance, `Dataset` caches results for `probe()` and `to_dataframe()` calls.

```python
# Clear internal cache if the dataset changes
ds.invalidate_cache()
```
