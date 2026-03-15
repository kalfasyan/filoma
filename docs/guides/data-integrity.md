# Dataset Integrity & Quality

Filoma provides a comprehensive suite of tools for maintaining dataset integrity and quality, encompassing file-level hashing/verification and content-level data science quality checks.

## Part 1: Dataset Integrity (Snapshots & Manifests)

Filoma provides two ways to capture and verify the state of a dataset on disk:

- **Snapshots**: fast, multi-level integrity checks over a directory tree.
- **Manifests**: full file metadata + hashes, designed for reproducibility and lineage.

Both are verified using the unified `verify_dataset` tool.

```python
import filoma.core.verifier as vrf

# Works for both saved 'snapshot.json' and 'manifest.json' files
results = vrf.verify_dataset("data_reference.json", target_path="./data")
```

### Dataset Snapshots

Use the top-level helpers for quick integrity checks:

```python
import filoma as flm

# Create a fast snapshot (size + mtime + filename) of a directory
snap = flm.snapshot("./data", mode="fast", export="snapshot.json")
```

Snapshot modes:

- `"fast"`: hash of filename + size + mtime (default; very fast).
- `"deep"`: fast hash + partial content hash (first/last 4KB).
- `"full"`: full SHA-256 of every file (audit-grade).

### Manifests

Manifests operate on `filoma.DataFrame` objects and are ideal for reproducible, hash-verified descriptions of your dataset including lineage.

```python
import filoma as flm
from filoma.core.manifest import Manifest

# Build a DataFrame from a directory
df = flm.probe_to_df("./data", enrich=True)

manifest = Manifest()
data = manifest.generate(df, compute_hashes=True)
manifest.save(data, "manifest.json")
```

---

## Part 2: Dataset Quality & Consistency Checks

Beyond file integrity, `DatasetVerifier` flags higher-level dataset issues such as corrupt files, inconsistent dimensions, or leakage.

### Key Quality Checks

- **Integrity**: Flag zero-byte files and images that fail to open.
- **Dimensions**: Detect inconsistent image sizes and report outliers.
- **Duplicates**: Identify near-duplicate images using perceptual hashing.
- **Class Balance**: Analyze your label CSVs to see class distribution.
- **Cross-Split Leakage**: Detect files appearing in more than one train/valid/test split.
- **Pixel Stats**: Flag images with anomalous pixel statistics (e.g., all black or white).

### How to use

```python
from filoma.core.verifier import DatasetVerifier

# Initialize with your dataset path
verifier = DatasetVerifier("/path/to/dataset")

# Run all quality checks
results = verifier.run_all(label_source="auto")

# Print a formatted summary table
verifier.print_summary()

# Export the results as JSON
verifier.export_report("dataset_quality.json", format="json")
```
