# Core Concepts

`filoma` focuses on fast, ergonomic filesystem analysis. Four high-level helpers cover 90% of use cases:

| Helper | Purpose | Returns |
|--------|---------|---------|
| `probe(path)` | Analyze a directory (or dispatch to file) | DirectoryAnalysis or File dataclass |
| `probe_to_df(path)` | Analyze + return Polars DataFrame | polars.DataFrame |
| `probe_file(path)` | Single file metadata | File dataclass |
| `probe_image(path|ndarray)` | Image stats/metadata | ImageReport |

Key object types:
- **DirectoryAnalysis**: structured dict-like result with summary + counts.
- **filoma.DataFrame**: thin wrapper over Polars with filesystem helpers.
- **File dataclass (Filo)**: metadata (size, ownership, times, hash, etc.).
- **ImageReport**: metadata + numeric stats for images / arrays.

Backends (auto-selected): Rust > fd > Python. You usually don’t choose manually.

Design goals:
- Minimal surface: few verbs, predictable results.
- Opt-in cost: heavy metadata/hash only if you ask.
- DataFrame-first: move seamlessly into Polars for analysis.
- Deterministic ML splits: grouping-aware to prevent leakage.

When in doubt: start with `probe('.')`, then `probe_to_df('.')` if you need tabular work.
