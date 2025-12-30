# Roboflow Dataset Analysis

This tutorial demonstrates how to use **Filoma** to analyze a computer vision dataset downloaded from Roboflow.

You can view the interactive notebook here:
[Roboflow Dataset Analysis Demo (HTML)](roboflow_demo.html)

### What this demo shows:

1.  **Downloading a dataset** using the Roboflow API.
2.  **Probing the dataset structure** and metadata using Filoma's `probe_to_df`.
3.  **Using Polars** for efficient data manipulation (filtering by extension, extracting path components).
4.  **Visualizing file size distributions** across dataset splits (train/valid/test) to identify potential data quality issues or augmentations.
5.  **Sampling and displaying images** from different splits.

### Key Snippet

```python
import filoma as flm
import polars as pl

# Create a DataFrame with file metadata
df = flm.probe_to_df("./dataset_path").filter_by_extension(".jpg")

# Extract the dataset split from the path
df = df.with_columns(split=pl.col("parent").str.split("/").list.last())

# Analyze file sizes by split
stats = df.group_by("split").agg(
    total_mb=(pl.col("size_bytes").sum() / (1024 * 1024)),
    avg_mb=(pl.col("size_bytes").mean() / (1024 * 1024))
)
print(stats)
```
