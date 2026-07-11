# Quickstart

`filoma` is **Dataset CI for ML** — go from folder to verified dataset to insights to agent, in one pipeline. It combines fast filesystem scanning, DataFrame enrichment, deduplication, quality gates, and an AI agent that understands your filesystem.

## Installation

```bash
uv add filoma          # recommended
pip install filoma     # classic pip works too
```

Want the fastest scanning? Install Rust or `fd` on your system — filoma auto-detects both and falls back to pure Python if neither is available.

## Choose your path

Pick the persona that matches what you're trying to do. Each tab is a self-contained 5-minute first run.

=== "ML Engineer"

    You want to verify a dataset before training. Corruption checks, duplicate detection, class balance — in one command, wired into CI.

    ```bash
    # One-line audit with HTML report
    filoma audit ./data --export audit-report.html

    # With quality gates
    filoma audit ./data --gates filoma-gates.yml
    ```

    **Python API:**

    ```python
    import filoma as flm

    pipeline = flm.Pipeline("./data").scan().enrich().verify().dedup().report()
    result = pipeline.audit()
    print(result.summary)
    ```

    **Next steps:** [Audit a Dataset](../use-cases/audit.md) — quality gates, GitHub Actions, CI integration.

=== "Data Engineer"

    You've been handed a folder — maybe 50 GB, maybe something weird. You need a DataFrame, fast.

    ```python
    import filoma as flm

    # Scan and get a Polars DataFrame with enrichment
    dfw = flm.probe_to_df("./data", enrich=True)

    # Filter, sort, export
    py_files = dfw.filter_by_extension(".py")
    large = dfw.df.sort("size", descending=True).head(10)
    print(dfw.extension_counts())
    dfw.save_parquet("inventory.parquet")
    ```

    **CLI quick peek:**

    ```bash
    filoma             # interactive file browser (arrow keys, Rich UI)
    filoma ./data      # start in a specific directory
    ```

    **Next steps:** [Explore a Dataset](../use-cases/explore.md) — profiling, filtering, aggregation workflows.

=== "Researcher"

    You want to ask your filesystem questions in natural language. No code, no API keys.

    ```bash
    # One-shot queries
    filoma ask "how many Python files are in this project?"
    filoma ask "find corrupted images in ./data"

    # Interactive chat (needs Ollama or API key)
    filoma filaraki chat

    # Setup wizard
    filoma setup
    ```

    **Local setup (no cloud):**

    ```bash
    ollama pull gemma4:e4b
    ollama serve
    filoma filaraki chat
    ```

    ```python
    import filoma as flm
    answer = flm.ask("audit ./data and show me the top 3 data quality issues")
    print(answer)
    ```

    **Next steps:** [Talk to Your Data](../use-cases/agent.md) — provider setup, MCP server, example dialogues.

## All three personas? You're covered.

filoma's Pipeline unifies everything:

```python
import filoma as flm

result = (
    flm.Pipeline("./dataset")
    .scan()          # explore: what's in here?
    .enrich()        # data eng: add path components, stats
    .dedup()         # find duplicates
    .verify()        # ML eng: integrity checks
    .report()        # HTML audit report
    .run()
)
```

## Key features

- **Fast scans**: Rust backend and `fd` for high-performance directory traversal.
- **DataFrame-first**: Polars-native wrapper with enrichment helpers (depth, path components, file stats).
- **Dedup**: Exact (SHA-256), text near-duplicates (k-shingles), image near-duplicates (perceptual hashing).
- **Quality gates**: `filoma-gates.yml` policy file with pass/fail exit codes for CI.
- **Agentic interface**: `filoma ask`, `filoma filaraki chat`, MCP server for any AI assistant.
- **Lazy loading**: `import filoma` is fast; heavy dependencies load on demand.

## Where to go next

- [Comparisons: Why filoma over X?](comparisons.md) — how filoma fits alongside `fd`, Polars, `great_expectations`, etc.
- [Cookbook](../tutorials/cookbook.md) — copy-paste recipes for common tasks.
- [Core Concepts](../guides/concepts.md) — the mental model behind filoma.
- [API Reference](../reference/api.md) — full function and class documentation.
