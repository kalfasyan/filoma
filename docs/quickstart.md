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

Lazy imports and top-level helpers

- filoma keeps imports lightweight: `import filoma` is intentionally cheap and does not import heavy optional dependencies like `polars` or `Pillow` until you actually use features that need them.
- Use the top-level helpers (`probe`, `probe_to_df`, `probe_file`, `probe_image`) for a terse, REPL-friendly API; these helpers will import required backends on demand.

Building docs (local):

```bash
# Install pinned docs deps (CI-friendly)
uv pip install -r docs/requirements-docs.txt

# Build the site
# Run the local mkdocs build (use your environment's mkdocs executable)
mkdocs build --clean
```
