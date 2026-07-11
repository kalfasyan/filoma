# Why filoma over X?

filoma is not a general-purpose data-quality framework, a file finder, or a dataframe library. It occupies a specific niche: **Dataset CI for ML** — taking a folder and turning it into a verified, deduplicated, profiled dataset you can talk to, in one pipeline.

This page compares filoma to tools that overlap in parts of that pipeline. The goal is honest comparison, not marketing. Every tool here is excellent at what it was designed for.

## Comparison matrix

| Dimension                  | **filoma**                                            | `fd` / `du`                                   | raw Polars            | `pandas-profiling`                  | `great_expectations`         |
| -------------------------- | ----------------------------------------------------- | --------------------------------------------- | --------------------- | ----------------------------------- | ---------------------------- |
| **Speed (directory scan)** | Rust / `fd` fallback — sub-second on 100k files       | `fd`: fastest in class; `du`: disk-usage only | No directory scanning | No directory scanning               | No directory scanning        |
| **DataFrame output**       | Polars-native wrapper with enrichment helpers         | None                                          | Core strength         | pandas-profiling generates profiles | Expectation Suites on pandas |
| **Dedup**                  | Exact + text near-dupes + image near-dupes            | None                                          | Manual                | None                                | None                         |
| **Data integrity**         | Snapshots + manifests + SHA-256 verification          | None                                          | Manual                | Column-level profiling only         | Expectation-level only       |
| **Quality gates (YAML)**   | Built-in `filoma-gates.yml` with pass/fail exit codes | None                                          | None                  | None                                | Expectations as code only    |
| **Agentic interface**      | `filoma ask`, Filaraki chat, MCP server               | None                                          | None                  | None                                | None                         |
| **Local-first**            | Yes — Ollama auto-detected, no cloud required         | Yes                                           | Yes                   | Yes                                 | Yes (self-hosted)            |
| **ML dataset focus**       | Class balance, leakage detection, split auditing      | None                                          | General-purpose       | General-purpose EDA                 | Data validation (any domain) |
| **CI/CD integration**      | GitHub Action + exit codes                            | None                                          | None                  | None                                | CI-friendly                  |
| **Reporting**              | HTML/JSON/MD audit reports with KPIs                  | None                                          | None                  | HTML profile reports                | Data Docs (HTML)             |

## When to use filoma

- You inherit a folder of 50 GB of images and CSVs and need to know what's in it **right now**.
- You train ML models and want a CI check that runs before every training job: "are there new corrupted files? Is the class balance still acceptable? Are there duplicates I don't know about?"
- You want to ask your filesystem questions in natural language (`filoma ask "how many corrupt images are in ./data?"`).
- You need file-level deduplication (exact, near-duplicate text, near-duplicate images) as part of your data prep.

## When to use something else

- **`fd`**: If all you need is "find all `.jpg` files recursively, fast." filoma wraps `fd` internally and adds metadata, but `fd` alone is 30 KB and has zero overhead.
- **`du`**: Disk usage summaries. filoma gives you file counts and sizes, but `du` is pre-installed everywhere.
- **raw Polars**: If you already have a DataFrame and just need filtering/aggregation, skip filoma's wrapper and use Polars directly. filoma's DataFrame helpers (`add_path_components`, `add_depth_col`) are conveniences for filesystem-centric workflows.
- **`pandas-profiling` / `ydata-profiling`**: If you need column-level EDA (histograms, correlations, missing-value analysis) on tabular data. filoma does file-level profiling, not column-level statistics.
- **`great_expectations`**: If you need a full data-validation framework with Expectation Suites, data docs, and a validation store. filoma's quality gates are simpler and filesystem-focused; great_expectations is the right choice for complex column-level constraints across databases.

## The key difference

filoma is the only tool in this comparison that combines **fast directory scanning + DataFrame enrichment + dedup + integrity/manifest + quality gates + an agentic interface** in a single pipeline. If your workflow touches 2+ of those dimensions, filoma replaces 3-4 separate tools. If you only need one, the specialized tool is likely the better fit.
