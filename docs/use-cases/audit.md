# Audit a Dataset

You have a dataset directory. Before training, you want to know: are there corrupted files? Duplicates? Is the class balance off? Should I be worried about anything?

This page walks through auditing a dataset with filoma, from one-line CLI to CI integration.

## One-line audit

```bash
filoma audit ./data --export audit-report.html
```

This runs corruption checks, hygiene scoring, migration readiness, and duplicate detection, then writes a self-contained HTML report. The exit code is non-zero if any quality gate fails, so it wires directly into CI.

## Programmatic audit

The same workflow via the Python API:

```python
import filoma as flm

pipeline = flm.Pipeline("./data").scan().enrich().verify().dedup().report()
result = pipeline.audit()
print(result.summary)
```

Each stage can be run independently:

```python
pipeline = flm.Pipeline("./data")
pipeline.scan()       # fast directory walk (Rust / fd backends)
pipeline.enrich()     # add depth, path components, file stats
pipeline.verify()     # snapshot integrity, corruption scan
pipeline.dedup()      # exact + near-duplicate detection
pipeline.report()     # HTML / JSON / MD export
```

See the [Dataset Management guide](../guides/dataset.md) and [Data Integrity guide](../guides/data-integrity.md) for deep-dive API reference.

## Quality gates with `filoma-gates.yml`

Define pass/fail thresholds in a YAML policy file:

```yaml
version: 1
gates:
  duplicate_ratio_pct: 1.0 # fail if >1% duplicates
  corrupted_files: 0 # fail if any corrupted
  zero_byte_files: 0 # fail if any zero-byte files
  hygiene_score: 70 # fail if hygiene score < 70
  migration_readiness: 80 # fail if readiness < 80
  class_min_samples: 50 # fail if any class < 50 samples
```

Run with gates:

```bash
filoma audit ./data --gates filoma-gates.yml
```

If any gate fails, the exit code is 1. The report shows which gates passed and which didn't, with actual vs. threshold values.

[Source: `src/filoma/core/gates.py`](https://github.com/filoma/filoma/blob/main/src/filoma/core/gates.py)

## GitHub Actions integration

filoma ships a composite GitHub Action that runs an audit and posts the report as a PR comment.

```yaml
name: Dataset Audit
on: [pull_request]
jobs:
  audit:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
    steps:
      - uses: actions/checkout@v4
      - uses: filoma/filoma/.github/actions/filoma-audit@main
        with:
          path: ./data
          gates: filoma-gates.yml
          export_format: html
```

The action:

- Installs filoma and its dependencies
- Runs `filoma audit` with your gates policy
- Posts the HTML report as a PR comment
- Fails the check if gates don't pass

For the action source, see [`.github/actions/filoma-audit/action.yml`](https://github.com/filoma/filoma/blob/main/.github/actions/filoma-audit/action.yml).

## Interpreting results

An audit report includes:

| Section                 | What it tells you                                                 |
| ----------------------- | ----------------------------------------------------------------- |
| **Corruption scan**     | Number of files that fail to open or are zero-byte                |
| **Hygiene score**       | 0-100 quality score: duplicates, depth outliers, extension noise  |
| **Migration readiness** | Blockers preventing dataset migration (e.g., mixed image formats) |
| **Duplicate groups**    | Groups of exact or near-duplicate files with sizes                |
| **Class balance**       | Per-class sample counts (from label CSVs found in-tree)           |

## Exit codes

| Code | Meaning                                                       |
| ---- | ------------------------------------------------------------- |
| 0    | All checks passed                                             |
| 1    | One or more gate failures                                     |
| 2    | Audit execution error (missing path, permission denied, etc.) |

## What to read next

- [Data Integrity & Quality guide](../guides/data-integrity.md) — API-level details on snapshots, manifests, and `DatasetVerifier`
- [Dataset Management guide](../guides/dataset.md) — fluent `Dataset` / `Pipeline` API
- [Explore a Dataset](explore.md) — if you want to explore first, audit later
