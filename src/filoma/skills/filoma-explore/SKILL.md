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
than per-file detail.

### 3. Enriched DataFrame (most powerful)

```python
import filoma as flm

df = flm.probe_to_df(".", enrich=True)
df.filter_by_extension([".py", ".rs"])    # in-place chainable
df.extension_counts()                     # group-by extension
df.directory_counts()                     # group-by parent dir
df.sort("size_bytes", descending=True).head(5)
df.pandas                                 # pandas conversion (free)
```

Enriched columns include: `parent`, `name`, `stem`, `suffix`,
`size_bytes`, `modified_time`, `created_time`, `is_file`, `is_dir`,
`owner`, `group`, `mode_str`, `inode`, `nlink`, `sha256`, `xattrs`,
`depth`. `sha256` and `xattrs` are populated only when explicitly
requested.

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
(df.filter_by_extension([".npy"])
   .sort("size_bytes", descending=True)
   .head(10))

# Files owned by a specific user
df.filter_by_pattern(r".*\.log$").filter(pl.col("owner") == "alice")

# Files modified in the last week
import datetime as dt
cutoff = dt.datetime.now() - dt.timedelta(days=7)
df.filter(pl.col("modified_time") > cutoff)
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
