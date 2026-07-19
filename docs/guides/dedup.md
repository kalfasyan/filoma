**Duplicate Detection**

This project includes a lightweight duplicate-detection helper available at `src/filoma/dedup.py`.

- **Exact duplicates**: `compute_sha256(path)` and `find_duplicates(paths)` detect byte-for-byte duplicates.
- **Text near-duplicates**: uses k-shingles and Jaccard similarity. Configure `text_k` and `text_threshold`.
- **Image near-duplicates**: basic perceptual hashing (aHash/dHash) using Pillow. Configure `image_hash` and `image_max_distance`.

Examples:

```
from filoma import dedup

files = ["data/a.jpg", "data/b.jpg", "data/c.txt"]
res = dedup.find_duplicates(files, text_threshold=0.8, image_max_distance=6)
print(res["exact"])  # exact matches
print(res["text"])   # near-duplicate text groups
print(res["image"])  # near-duplicate image groups
```

Optional dependencies:

- `Pillow` — recommended for image hashing.
- `datasketch` — optional for MinHash acceleration on large text datasets.

## Finding near-duplicate/mirrored folders cheaply

A common real-world situation: a dataset directory contains a full copy
of itself nested somewhere (e.g. an "augmented" export that also bundles
the original images), which shows up as thousands of exact-duplicate file
groups. Reading that report file-by-file is expensive — both for a human
and for an agent burning tokens on a multi-megabyte report.

`summarize_duplicate_directories()` rolls file-level duplicate groups up
into directory-pair overlap stats instead, answering "are these two
folders near-duplicates?" in a handful of lines regardless of how many
duplicate files exist:

```python
from filoma import dedup

res = dedup.find_duplicates(all_file_paths)
overlap = dedup.summarize_duplicate_directories(
    res["exact"],
    all_paths=all_file_paths,  # optional, enables overlap_pct
)
for pair in overlap[:5]:
    print(pair["dir_a"], "<->", pair["dir_b"], pair["shared_files"], f"{pair['overlap_pct']}%")
```

Each entry is `{"dir_a", "dir_b", "shared_files", "dir_a_total_files", "dir_b_total_files", "overlap_pct"}`, sorted by `shared_files` descending. A pair near 100% overlap with a non-trivial shared-file count is a strong signal of a mirrored/near-duplicate folder tree.

This is also wired into the `find_duplicates` agent/MCP tool:

- The default report now caps the file-level listing (50 groups) instead of dumping every duplicate file, and proactively prints a **"POSSIBLE NEAR-DUPLICATE / MIRRORED DIRECTORIES"** section up top whenever a directory pair has ≥90% overlap — no follow-up question needed.
- Pass `group_by_directory=True` for the full compact directory-pair breakdown instead of the file-level report.
