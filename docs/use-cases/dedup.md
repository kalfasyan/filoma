# Deduplicate a Dataset

Duplicate files waste storage, skew training distributions, and inflate your validation metrics. filoma detects exact duplicates, near-duplicate text, and near-duplicate images in one pass.

## Quick start

```python
import filoma as flm

pipeline = flm.Pipeline("./data").scan().dedup()
results = pipeline.dedup()

print("Exact duplicates:", results["exact"])
print("Near-duplicate text:", results["text"])
print("Near-duplicate images:", results["image"])
```

Or find duplicates on a specific list of files:

```python
from filoma import dedup

files = ["data/a.jpg", "data/b.jpg", "data/c.jpg", "data/notes.txt"]
results = dedup.find_duplicates(
    files,
    text_threshold=0.8,
    image_max_distance=6,
)

for group in results["image"]:
    print(f"Similar images: {group}")
```

## Three levels of dedup

### 1. Exact duplicates (SHA-256)

Byte-for-byte identical files. Fast and definitive — if two files have the same SHA-256 hash, they're the same file regardless of name or location.

### 2. Near-duplicate text

Uses k-shingles (overlapping character n-grams) and Jaccard similarity. Two text files with `text_threshold=0.8` are flagged if 80% of their shingle sets overlap. This catches files where someone changed a few lines or renamed variables.

Tune with `text_k` (shingle size, default 5) and `text_threshold` (0.0-1.0, default 0.8).

### 3. Near-duplicate images

Uses perceptual hashing (aHash or dHash) via Pillow. Two images with a Hamming distance at or below `image_max_distance` are flagged as near-duplicates. This catches resized, slightly cropped, or re-compressed copies.

Tune with `image_hash` (`"ahash"` or `"dhash"`, default `"dhash"`) and `image_max_distance` (0-64, default 10 for dHash).

## Using with Pipeline

The dedup stage integrates into the full pipeline:

```python
import filoma as flm

pipeline = (
    flm.Pipeline("./dataset")
    .scan()
    .enrich()
    .dedup(
        text_threshold=0.85,
        image_max_distance=6,
        image_hash="dhash",
    )
    .verify()
    .report()
)

result = pipeline.run()
print(f"Found {len(result.duplicates)} duplicate groups")
```

## Interpreting results

Each result is a list of groups, where each group is a list of file paths that are duplicates of each other:

```python
results = flm.dedup.find_duplicates(files)

# Exact: [["a.jpg", "a_copy.jpg"], ["b.txt", "b_old/b.txt"]]
# Text:  [["notes_v1.txt", "notes_v2.txt"]]
# Image: [["photo.jpg", "photo_resized.jpg", "photo_compressed.jpg"]]
```

Action suggestions:

- **Exact duplicates**: Keep one, delete the rest (or symlink).
- **Near-duplicate text**: Review manually — might be legitimate revisions.
- **Near-duplicate images**: Check if they're data-augmentation artifacts. In training datasets, near-duplicates across train/val/test splits are a leakage risk.

## Performance notes

- SHA-256 hashing reads every byte of every file — plan for I/O time on large datasets.
- Perceptual hashing needs Pillow (`pip install Pillow`).
- For very large text collections, optional `datasketch` MinHash acceleration reduces Jaccard computation from O(n^2) to O(n). Install with `pip install datasketch`.

## What to read next

- [Duplicate Detection guide](../guides/dedup.md) — full API reference and parameter details
- [Explore a Dataset](explore.md) — find the files you want to dedup
- [Audit a Dataset](audit.md) — include dedup in a quality gates workflow
