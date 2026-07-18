---
name: filoma-explore
description: Explore directories with filoma — count files, find largest files, group by extension or owner, build enriched Polars DataFrames of filesystem metadata, and ask natural-language questions about a folder. Use when the user asks "what's in this folder", to count files in a directory, list the largest files, group files by extension / size / mtime / owner, build a DataFrame of file metadata, get directory statistics, profile a single file or image, or chat with their filesystem in plain English. Requires filoma installed.
---

# Filoma Explore

Use this skill when the user is poking around a directory they don't
fully know — counting things, finding the biggest files, grouping by
extension, or just asking "what's in here?". Filoma is the fastest way
to answer that without writing a `find | xargs | awk` chain.

## When to use this skill

Trigger on:

- "how many files are in <path>?"
- "what's in this folder?"
- "show me the largest files / biggest images / oldest logs"
- "group files by extension / owner / mtime"
- "give me a DataFrame of file metadata"
- "how big is this directory?"
- "what's the largest .jpg in this tree?"
- single-file metadata: "info about this file", "what kind of image is X"
- free-form: "let me ask my filesystem things"

Do **not** use this skill for:

- Dataset audit / training-readiness → use `filoma-dataset-ci`.
- Duplicate detection → use `filoma-dedup`.

## Three idioms, in order of laziness

### 1. Natural language (most ergonomic)

```bash
filoma ask "how many python files are here, and what's the largest?"
filoma chat                       # interactive REPL
```

```python
import filoma as flm
flm.ask("how many python files are here?").output
```

`flm.ask(...)` auto-spins up a Filaraki agent rooted at the current
directory. It uses Ollama by default if running, or any of
`MISTRAL_API_KEY` / `GEMINI_API_KEY` / `OPENAI_API_KEY`. If the user
hasn't configured a provider yet, run `filoma setup` first.

### 2. High-level summary

```python
import filoma as flm

analysis = flm.probe(".")
analysis.print_summary()          # rich table: counts, sizes, top exts
analysis.print_report()           # detailed: extensions + folder stats
```

This is the right call when the user wants "overall stats" rather
than per-file detail. **Call `probe()` once and reuse the returned
`analysis` object for both calls** — each `probe()` re-walks the
entire directory tree, so invoking it twice (e.g. in two separate
shell/python calls) doubles the scan cost for no benefit.

### 3. Enriched DataFrame (most powerful)

```python
import filoma as flm

df = flm.probe_to_df(".", enrich=True)
print(df.filter_by_extension([".py", ".rs"]))    # returns a NEW DataFrame
print(df.extension_counts())                       # group-by extension
print(df.directory_counts())                       # group-by parent dir
print(df.sort("size_bytes", descending=True).head(5))
df.pandas                                          # pandas conversion (free)
```

**Every filter / sort / group method above returns a new `DataFrame`
— none of them mutate `df` in place.** A bare
`df.filter_by_extension([...])` statement with no assignment or
`print(...)` silently does nothing to `df` and produces no visible
output; always do `df = df.filter_by_extension([...])` or chain /
print the return value directly, especially when running a snippet
as a one-shot script (e.g. `python3 -c "..."`).

Enriched columns include: `parent`, `name`, `stem`, `suffix`,
`size_bytes`, `modified_time`, `created_time`, `is_file`, `is_dir`,
`owner`, `group`, `mode_str`, `inode`, `nlink`, `sha256`, `xattrs`,
`depth`. `sha256` and `xattrs` are populated only when explicitly
requested.

### Per-row quality columns

Duplicate/corruption checks aren't just aggregate reports \u2014 they can be
attached directly to the DataFrame as queryable columns, so you can
filter/sort/count on them like any other column:

```python
df = flm.probe_to_df(".", enrich=True)
df = df.add_duplicate_cols()    # adds is_exact_duplicate, exact_dup_group_id (sha256-based)
df = df.add_corruption_cols()   # adds is_corrupt, corruption_reason (zero-byte / unreadable images)

print(df.filter(pl.col("is_exact_duplicate")))   # only the duplicate rows
print(df.filter(pl.col("is_corrupt")))           # only corrupt/zero-byte rows
```

`add_duplicate_cols()` computes sha256 automatically if not already
present (reads full file content \u2014 slow on huge datasets). Only exact
(byte-identical) duplicates are covered today; visual near-duplicates
(perceptual hash) and text near-duplicates (MinHash) are not yet
columns here \u2014 use the `filoma-dedup` skill for those until that lands.

## Single-file probing

```python
flm.probe_file("README.md")       # generic file metadata
flm.probe_image("photo.jpg")      # adds shape, dtype, pixel stats
flm.probe(".")                    # auto-dispatches: file → probe_file,
                                  # dir → probe directory
```

`flm.probe(...)` dispatches based on the path type, so "probe this
thing" without thinking about file-vs-directory is the right reflex.

## Backend selection (rarely needs explanation)

Filoma auto-picks the fastest available backend in this order:

1. **Rust (Parallel)** — built-in, fastest on most workloads
2. **fd** — used if the `fd` binary is on PATH (great for huge trees
   over network mounts)
3. **Python** — pure stdlib fallback, always works

Only mention backends if the user asks why something is slow.

## Filtering recipes

```python
df = flm.probe_to_df("data/", enrich=True)

# Largest 10 .npy files
largest_npy = (df.filter_by_extension([".npy"])
                 .sort("size_bytes", descending=True)
                 .head(10))
print(largest_npy)

# Files owned by a specific user
alice_logs = df.filter_by_pattern(r".*\.log$").filter(pl.col("owner") == "alice")
print(alice_logs)

# Files modified in the last week
import datetime as dt
cutoff = dt.datetime.now() - dt.timedelta(days=7)
recent = df.filter(pl.col("modified_time") > cutoff)
print(recent)
```

## Performance tips

- `import filoma` is cheap — submodules load lazily. Don't write
  `from filoma.directories import ...` at module top unless needed.
- For directories with millions of files, `enrich=True` is slower
  because it stat-calls every entry. Drop it if the user only needs
  paths.
- `flm.probe(...)` returns a `DirectoryAnalysis` dataclass with a
  `.summary` dict and a `.df` field — use the dataframe for ad-hoc
  questions, the summary for headline numbers.
