---
name: filoma-dataset-ci
description: Audit ML datasets for training readiness using filoma. Use when the user asks to audit a dataset, run a dataset health check, validate a folder of training data before training, generate a dataset audit report (HTML/JSON/Markdown), check for corrupt or zero-byte files, generate a hygiene report, or assess dataset migration readiness. Covers integrity, hygiene (duplicate ratio, class balance), and produces a self-contained interactive HTML report. Requires filoma installed (`pip install filoma` or `uvx filoma`).
---

# Filoma Dataset CI

Use this skill when the user wants to verify that a folder of training
data is safe to train on, or wants a one-shot audit report of an
existing dataset. Filoma calls this **"Dataset CI for ML"** — the
single pipeline that goes from a raw folder to a verified, scored,
HTML-rendered audit.

## When to use this skill

Trigger on any of these intents:

- "audit my dataset" / "run a dataset audit"
- "is this dataset ready to train on?"
- "check data quality before training"
- "find corrupt / zero-byte files in this folder"
- "generate a hygiene report for this directory"
- "score this dataset's migration readiness"
- "give me an HTML report of this folder"

Do **not** use this skill for:

- Single-file inspection → use `filoma-explore` (probe one file).
- Pure duplicate detection → use `filoma-dedup` (focused, faster).
- Free-form filesystem questions → use `filoma-explore` or
  `filoma ask "..."`.

## Quick start (one command)

If the user has no dataset handy, prove the pipeline works in seconds:

```bash
filoma demo
```

This generates a tiny synthetic fixture, runs the full pipeline, and
opens a self-contained HTML audit report in the browser.

## Headline workflow

For a real dataset at `<path>`:

```bash
# CLI — most common
filoma audit <path>                 # exits 0 on pass, non-zero on fail (CI-ready)
```

Or, equivalently, from Python:

```python
import filoma as flm

pipeline = flm.Pipeline("<path>").scan().enrich().verify().report()
print(pipeline.report_path)              # → /tmp/<folder>_audit.html
print("rows:", pipeline.dataframe.df.height)
```

The four stages produce, in order:

| Stage    | What it checks                            | Output                          |
| -------- | ----------------------------------------- | ------------------------------- |
| `scan`   | Walks the tree (Rust → fd → Python)       | counts + file list              |
| `enrich` | Adds size / mtime / owner / sha256 / etc. | enriched Polars DataFrame       |
| `verify` | Snapshot + manifest integrity             | matched / missing / extra lists |
| `report` | Hygiene + readiness + corruption          | HTML / JSON / Markdown          |

## Reading the HTML report

The exported HTML contains:

- **Score gauges** — Hygiene + Migration Readiness (0–100)
- **KPI strip** — file count, duplicate groups, wasted space
- **Stage timing bars** — integrity / hygiene / readiness
- **Priority-tagged Next Actions** — high (red) / medium (amber) / low
- **Duplicate evidence cards** — exact paths, grouped
- **Collapsible JSON payload** — for machine consumption

Export formats: `html`, `json`, `md`. JSON / MD are useful for posting
to a PR comment in CI.

## Programmatic export

```python
from filoma.filaraki.tools import audit_dataset
audit_dataset(None, "<path>", export_path="audit.html", export_format="html")
audit_dataset(None, "<path>", export_path="audit.json", export_format="json")
```

## Targeted sub-audits

When the user only wants one slice:

- `audit_corrupted_files(<path>)` — zero-byte, broken images, etc.
- `generate_hygiene_report(<path>)` — duplicate ratio, class balance, naming
- `assess_migration_readiness(<path>)` — readiness score with actions

These are the exact tools the full audit composes; expose them
individually when the user's question is narrow.

## CI/CD usage

`filoma audit` exits non-zero when quality gates fail, so it drops
into GitHub Actions, GitLab CI, or any shell pipeline. Pair with
`--export-format json` to post structured results.

## Notes

- `import filoma` is intentionally lightweight; heavy deps load on
  demand. Don't pre-import submodules "just in case".
- Backends auto-select. The user does not need to pick one. If they
  want maximum speed on huge trees, `apt install fd-find` /
  `brew install fd` enables the fd backend.
- When the dataset is on a slow network share, the whole pipeline
  re-walks the tree multiple times today — that's a known speedup
  on the roadmap, not a bug. Warn the user if the report is slow on
  > 1M files.
