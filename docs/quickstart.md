# Quickstart

`filoma` is a fast and flexible Python tool for filesystem analysis. It helps you understand the contents of your directories, profile individual files, and prepare datasets for machine learning.

## Getting Started: The Interactive Demo

The best way to get started with `filoma` is to run the interactive demo notebook. It covers the most common workflows in a hands-on way.

- **[View the Interactive Demo](./demo.md)**

## Installation

Install `filoma` and its dependencies using `uv` or `pip`:

```bash
# Recommended: using uv
uv pip install filoma

# Or with pip
pip install filoma
```

## Basic Usage: Scan a Directory

The most common use case is scanning a directory to see what's inside. The `probe_to_df` function scans a path and returns a [Polars](https://pola.rs/) DataFrame, which is great for interactive analysis.

```python
from filoma import probe_to_df

# Scan the current directory and get a DataFrame
df = probe_to_df('.')

# Print the first few rows
print(df.head())
```

This will give you a table with information about each file, like its path, size, and modification time.

## Profile a Single File

You can also get detailed information about a single file using `probe_file`:

```python
from filoma import probe_file

# Profile the README.md file
file_info = probe_file('README.md')

# Print the file's properties
print(file_info.as_dict())
```

## Key Features

- **Fast Scans**: Uses a Rust backend and `fd` for high-performance directory traversal.
- **DataFrame-First**: Easily integrates with the Polars for powerful data manipulation and analysis.
- **Image Profiling**: Extracts metadata from images.
- **ML-Ready**: Provides tools for creating deterministic train/validation/test splits from your file data.
- **Lazy Loading**: `import filoma` is fast and lightweight. Dependencies like `polars` and `Pillow` are loaded on demand.

## Where to Go Next

- **Cookbook**: Find copy-paste recipes for common tasks.
- **Concepts**: Learn about the core ideas behind `filoma`.
- **DataFrame Workflow**: See how to work with `filoma`'s DataFrame output.
