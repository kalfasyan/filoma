# Quickstart

This quickstart shows the most common, REPL-friendly workflow for `filoma`.

Install:

```bash
# Using uv (recommended)
uv add filoma

# Or editable install with docs extras for local docs building
uv pip install -e '.[docs]'
```

Basic directory scan and summary:

```python
from filoma import probe, probe_to_df

analysis = probe('.')
analysis.print_summary()

# Convert to a Polars DataFrame for exploration
df = probe_to_df('.', to_pandas=False)
print(df.head())
```

Profile a single file:

```python
from filoma import probe_file

f = probe_file('README.md')
print(f.as_dict())
```

Image profiling:

```python
from filoma import probe_image

img = probe_image('images/logo.png')
print(img.file_type, getattr(img, 'shape', None))
```

Tips
- Use `search_backend='fd'` or `search_backend='rust'` for faster scans when available.
- In notebooks, use `probe_to_df()` and then Polars APIs for interactive filtering and plots.

Building docs (local):

```bash
# Install pinned docs deps (CI-friendly)
uv pip install -r docs/requirements-docs.txt

# Build the site
/home/kalfasy/repos/filoma/.venv/bin/mkdocs build --clean
```
