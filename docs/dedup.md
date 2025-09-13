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