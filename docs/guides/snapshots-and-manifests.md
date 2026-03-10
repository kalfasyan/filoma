## Snapshots & Manifests

Filoma provides two complementary ways to capture and verify the state of a dataset on disk:

- **Snapshots**: fast, multi-level integrity checks over a directory tree.
- **Manifests**: full file metadata + hashes, designed for reproducibility and lineage.

### Dataset snapshots

Use the top-level helpers for quick integrity checks:

```python
import filoma as flm

# Create a fast snapshot (size + mtime + filename) of a directory
snap = flm.snapshot("./data", mode="fast", export="snapshot.json")
print(f"Captured {len(snap.entries)} files")

# Later: verify the directory against the saved snapshot
results = flm.verify_snapshot("snapshot.json")
print("Matched:", len(results["matched"]))
print("Modified:", len(results["modified"]))
print("Missing:", len(results["missing"]))
print("Added:", len(results["added"]))
```

Snapshot modes:

- `"fast"`: hash of filename + size + mtime (great default; very fast).
- `"deep"`: fast hash + partial content hash (first/last 4KB) for better corruption detection.
- `"full"`: full SHA-256 of every file (slowest; audit-grade).

You can also filter files and include metadata:

```python
snap = flm.snapshot(
    "./data",
    mode="deep",
    pattern="*.parquet",
    include_hidden=False,
    metadata={"project": "experiment-42"},
)
snap.save("data_snapshot.json")
```

### Manifests

Manifests operate on `filoma.DataFrame` objects and are ideal when you already have a
scanned dataset and want a reproducible, hash-verified description of it.

```python
import filoma as flm
from filoma.core.manifest import Manifest

# Build a DataFrame from a directory
df = flm.probe_to_df("./data", enrich=True)

manifest = Manifest()
data = manifest.generate(df, compute_hashes=True)
manifest.save(data, "manifest.json")
```

The manifest contains per-file records (`path`, `size_bytes`, `modified_time`, `sha256`)
plus a `summary` and the DataFrame `lineage`.

To verify a directory against a manifest:

```python
results = manifest.verify("manifest.json")
manifest.print_report(results)
```

Verification reports:

- `matched`: all files whose size and hash match.
- `missing`: files in the manifest that are not present on disk.
- `size_mismatch`: size differs from the manifest.
- `hash_mismatch`: size matches but content hash differs.

By default, relative paths in the manifest are resolved relative to the manifest file
location; use `root_path` if you need to verify against a different directory.
