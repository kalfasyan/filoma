---
name: filoma-dedup
description: Find duplicate files, duplicate images (perceptual hash), duplicate text files, and train/test data leakage in one or more directories using filoma. Use when the user mentions duplicate files, deduplicating a dataset, removing duplicates, finding identical or near-identical images, perceptual hashing, train/test leakage, cross-directory duplicate detection, or wants to deduplicate before training. Returns groups for three categories: exact (sha256), text (MinHash), and image (perceptual hash). Requires filoma installed.
---

# Filoma Dedup

Use this skill when the user wants to find or remove duplicate files,
or when they're worried about train/test leakage between two folders.
Filoma detects three kinds of duplicates and returns them as groups —
it never deletes anything; deletion is the user's call.

## When to use this skill

Trigger on:

- "find duplicate files in <path>"
- "deduplicate this folder"
- "are there duplicate images here?"
- "is there leakage between my train and validation sets?"
- "find near-duplicate / similar images" (perceptual hash)
- "find files that contain the same text" (MinHash on text)

Do **not** use this skill for:

- Full dataset audit including duplicates → use `filoma-dataset-ci`
  (it composes dedup with corruption + hygiene + readiness).
- General directory exploration → use `filoma-explore`.

## In-directory dedup

```bash
filoma dedup <path>
```

Returns three groups:

| Category | Detector           | Best for                       |
| -------- | ------------------ | ------------------------------ |
| `exact`  | sha256 byte match  | identical files (any type)     |
| `text`   | MinHash similarity | duplicate text/code/JSON       |
| `image`  | perceptual hash    | visually identical/near images |

Each group is a list of paths that match each other. The user picks
which to keep.

## Cross-directory dedup (train/test leakage)

This is the killer use-case. Two folders, find rows that appear in
both:

```bash
filoma dedup train/ valid/ --cross-dir
filoma dedup train/ valid/ test/ --cross-dir
```

`--cross-dir` only reports duplicate **groups that span at least two of
the provided directories**, so you get leakage candidates and only
leakage candidates. Without `--cross-dir`, you also get within-folder
duplicates.

## Programmatic API

When the user is in a notebook or script and wants the result as a
Python dict:

```python
import filoma as flm

# Single directory
ds = flm.Dataset("./my_data")
dupes = ds.dedup()
# dupes == {"exact": [...], "text": [...], "image": [...]}

# Or via a DataFrame already in memory
df = flm.probe_to_df("./my_data", enrich=True)
dupes = df.evaluate_duplicates(show_table=True)

# Cross-directory leakage
df = flm.probe_to_df(["train/", "valid/"])  # combine multiple paths
dupes = df.evaluate_duplicates(cross_dir_paths=["train/", "valid/"])
```

## Interpreting groups

- A "group" is a list of ≥2 paths that the detector marked as
  duplicates of each other.
- Exact dedup is deterministic. Text and image dedup use approximate
  matching, so review groups before deleting — false positives are
  rare but possible (especially for image dedup on heavily augmented
  data).
- For ML datasets, leakage groups (`--cross-dir`) are the highest-
  priority finding. Recommend the user remove duplicates from the
  validation set, not the training set, to preserve the held-out
  property of the eval set.

## Performance notes

- `exact` is sha256 — IO-bound. `find_duplicates` uses the Rust
  backend by default; on huge trees, install `fd` for a bit more.
- `image` is the slowest category because it needs to decode each
  image. Skip it via `df.evaluate_duplicates(image=False)` if the
  user only cares about exact matches.
- The optional `dedup` extra (`pip install filoma[dedup]`) brings in
  `datasketch` for MinHash. If the user gets ImportError on text
  dedup, that's the missing extra.

## Safety

Filoma never deletes files. The output is a report; deletion is the
user's responsibility. If the user asks you to delete duplicates,
**stop and confirm** which copy in each group should survive — there
is no canonical answer.
