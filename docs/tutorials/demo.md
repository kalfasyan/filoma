# filoma demo

Explore the core features of `filoma` through practical examples.

### Basic Probing

```python
import filoma

# Analyze current directory
analysis = filoma.probe(".")
print(analysis.summary())
```

### DataFrame Workflow

```python
# Scan and convert to DataFrame
df = filoma.probe_to_df("./data")

# Filter large files
large_files = df.filter(size_bytes > 1e6)
```

### Image Profiling

```python
# Get detailed image metadata and statistics
report = filoma.probe_image("photo.jpg")
print(report.stats)
```

Refer to the [Cookbook](cookbook.md) for more advanced usage examples.
