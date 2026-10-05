# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Filoma is a Python library with an optional Rust extension that profiles file trees, builds Polars DataFrames, verifies dataset integrity, finds duplicates, and exposes all of that to LLM agents (a pydantic-ai agent and an MCP server). `AGENTS.md` covers PR conventions, code conventions and the `filoma` vs `filoma-dev` MCP server gotcha, and `CONTRIBUTING.md` is the short human version. Read them too.

## Commands

Dev setup: `uv sync --extra dev --extra all` (or `pip install -e ".[dev,all]"`), then `maturin develop --release` to build the Rust extension. The base install is deliberately small, so the agent, RAG and pandas stacks live in optional extras and the tests need `all`. `import filoma` works without the Rust build and falls back to fd or pure Python, but the Rust parity tests are skipped and Rust changes have no effect until you rebuild. The built `filoma_core*.so` lands in `src/filoma/`. A bare `cargo build` may link against a different Python than your venv's and produce an unloadable `.so`; use maturin.

```bash
poe test                                   # pytest -n auto tests/ -m 'not integration'
pytest tests/test_foo.py::TestClass::test_name -v   # single test
pytest tests/test_lazy_imports.py          # must always pass
pytest tests/test_mcp_server.py            # after touching mcp_server.py / tool registration
pytest tests/test_engine_parity_generative.py   # every scan engine vs an os.scandir oracle (needs built extension)

poe lint                                   # ruff check .
poe lint-fix / poe format-fix              # ruff check --fix / ruff format
poe precommit                              # pre-commit run --all-files
poe check-skills                           # validate SKILL.md references against the CLI/API/registry
poe benchmark /path -n 3 --backend traversal   # args are forwarded as-is (no `--`)

cargo clippy --manifest-path Cargo.toml -- -D warnings   # pre-commit runs this; warnings fail
make docs-serve                            # renders notebooks, then mkdocs serve
make bump-patch                            # bumps src/filoma/_version.py AND pyproject.toml together
```

- Line length is 210 and pydocstyle (D rules) is enforced outside `tests/`, so public functions need docstrings.
- pre-commit also runs rustfmt, clippy, prettier, markdownlint, taplo and nbstripout. `--no-verify` is forbidden.
- CI (`.github/workflows/ci.yml`) has four jobs: pre-commit; lint and `pytest` on Python 3.11 to 3.14 with `pip install -e ".[all]"`; a `minimal-install` job (no extras, with a `filoma audit` smoke test); and a non-blocking macOS/Windows job. Installing from source goes through the maturin build backend, so it needs a Rust toolchain. Releases come from pushing a `v*` tag (`publish.yml`).
- `-m integration` tests need real LLM provider keys. Config comes from a gitignored `.env`; see `.env_example` for the provider priority (Ollama, Mistral, Gemini, then any OpenAI-compatible endpoint).
- `.kilo/`, `data/`, `dist/`, `site/`, `target/`, `node_modules/` and `.env` are gitignored local artifacts, not source.

## Architecture

### Lazy imports and optional extras are hard constraints

`src/filoma/__init__.py` resolves public names through a PEP 562 `__getattr__` (`Pipeline`, `Dataset`, `DataFrame`, `RagStore`, subpackages). The `probe`, `probe_to_df`, `snapshot`, `ask` and similar helpers import their implementation inside the function body. Polars, Pillow, pydantic-ai, mcp, openai and lancedb must not load on `import filoma` or `import filoma.filaraki`; `tests/test_lazy_imports.py` checks this in a fresh subprocess. Add new public API through `__getattr__` and `__all__`, not as a top-level import.

Core dependencies are only what scanning, DataFrames, integrity checks and `filoma audit` need. Extras: `agent` (pydantic-ai, mcp), `rag` (lancedb, sentence-transformers; pulls in PyTorch), `pandas`, `dedup`, `stats`, and `all`. Code that needs an extra must fail with an install hint (`pip install 'filoma[agent]'`), not a bare `ImportError`; the CLI uses `require_extra()` in `cli/_app.py`, and tests use `pytest.importorskip(...)`. `tests/test_core_without_optional_extras.py` and `tests/test_without_rust_extension.py` simulate lean and no-Rust installs by blocking the modules in a subprocess.

### Scan backends (Rust, fd, Python) and the Rust engines

`DirectoryProfiler` (`src/filoma/directories/directory_profiler.py`) takes a `DirectoryProfilerConfig` dataclass. It is the only orchestrator. Backend choice happens in two places that must stay consistent. `__init__` resolves `search_backend` and the `use_rust`/`use_fd` flags, validating explicit requests against the module-level availability flags (`RUST_AVAILABLE`, `RUST_ASYNC_AVAILABLE`, `FD_AVAILABLE`, ...). `_choose_backend` then reads those resolved flags. `use_parallel` defaults to True but is only a preference that resolves against availability; it must never raise. `fast_path_only` makes "auto" prefer Python. The implementations are `_probe_rust`, `_probe_fd` (via `core/fd_integration.py` and `directories/fd_finder.py`) and `_probe_python`; the two Python-based probes share `_assemble_probe_result`.

The Rust crate is `filoma-core`, built by maturin as the Python module `filoma.filoma_core` (`python-source = "src"`). It holds four engines:

- `src/lib.rs`: walkdir-based sequential and rayon-parallel engines, plus the `#[pymodule]`. The parallel one only engages with several top-level directories and walks each subtree separately, so it counts root-level files explicitly.
- `src/dua_scan.rs`: the dua-core parallel walker, the default local engine.
- `src/async_scan.rs`: the tokio scanner, default on network filesystems because of its timeouts and retries. Measured fixed overhead is roughly 0.7s per scan even on a tiny tree (its worker pool polls a shared queue); it is not a hang.

`walker="dua-core" | "walkdir" | "auto"` in the config picks the engine. The profiler always scans with `search_hidden=True` and never passes `follow_links=True`; those options are only reachable by calling the low-level `filoma_core` functions directly.

The engines, the Python backend and fd must return identical results. The contract is in `docs/reference/architecture.md` ("Engine harmonization contract": symlinks, `max_depth`, empty folders, hidden pruning, `max_depth`/`depth_distribution` as folder-only stats, the root keyed once). `tests/test_engine_parity_generative.py` is the authority: it builds random trees and compares every engine to an independent `os.scandir` oracle. When you change any engine, keep that test green and extend it. `follow_links=True` is not covered, and the sequential and parallel walkdir engines differ on symlink loops there.

### Data layer

- `filoma.DataFrame` (`dataframe.py`) wraps a Polars frame. `__getattr__` delegates to Polars and re-wraps results. The `add_*_cols` enrichers (depth, path components, file stats, duplicates, corruption, text/image/metadata embeddings, semantic similarity) return wrappers, and `add_lineage_entry` records provenance.
- `Pipeline` (`pipeline.py`) runs `Stage` objects (`ScanStage`, `EnrichStage`, `VerifyStage`, ...) that share one `PipelineState`, so `scan().enrich().verify().report()` walks the filesystem once. `Dataset` is a backward-compatible subclass that keeps the legacy `snap`/`probe`/`to_dataframe` API.
- `core/` holds the integrity and quality pieces: `snapshot.py` and `manifest.py` (fast/deep/full hash modes), `verifier.py`, `gates.py` (`filoma-gates.yml` thresholds for `filoma audit --gates`, exit code 1 on failure), `rag.py` (`RagStore`, LanceDB), `vision.py` (CLIP image embeddings), and `command_runner.py`. `dedup.py` handles exact, text and image near-duplicates.

### Agent surface: one ToolRegistry feeds two adapters

- `src/filoma/tool_registry.py` holds the `tool_registry` singleton. `@tool_registry.register` records each function's name, description and JSON schema. The schema is derived from the type hints plus the `Args:` block of the docstring, so docstring format and annotations are part of the tool's public contract. Registering an existing name silently replaces it.
- Third-party tools register through the `filoma.tools` entry-point group, discovered lazily (see `docs/guides/plugins.md` and `examples/plugin_example/`). The registry remembers which tools came from plugins (`plugin_tool_names()`), and an entry point that raises is skipped with a warning.
- All built-in tools are defined once in `src/filoma/filaraki/tools.py`. `FilarakiAgent` (`filaraki/agent.py`) passes every registered tool to a pydantic-ai `Agent` and builds its system prompt's tool list from the registry. Tools receive a pydantic-ai `RunContext[FilarakiDeps]`, and `FilarakiDeps` carries `current_df`, `rag_store` and the probe/DataFrame caches. Tool order is registration order, which is the order of the file, so splitting the module by domain changes what the model sees.
- `filoma audit` calls `audit_dataset(None, ...)` directly, with no agent. `tools.py` therefore falls back to a stand-in `RunContext` when pydantic-ai is missing; keep audit code paths free of `ctx` and agent imports. The HTML report is rendered by `filaraki/audit_report.py`.
- `src/filoma/mcp_server.py` exposes the allowlist `_MCP_TOOL_NAMES` plus all plugin tools; some built-ins (for example `list_directory`, `search_rag`, `run_quality_check`) are agent-only. It wraps calls in a `SimpleRunContext` and keeps `current_df` state per MCP session in `_dataframe_state`, so `_DATAFRAME_TOOLS` lists the tools that read or write that state. Under stdio transport, stdout is reserved for JSON-RPC, so loguru is redirected to stderr and tools check `FILOMA_MCP_STDIO`. Do not `print()` from tool code paths. Only stdio is implemented.

When adding a built-in tool:

- Register it in `filaraki/tools.py`.
- Add it to `_MCP_TOOL_NAMES` if the MCP server should expose it (and to `_DATAFRAME_TOOLS` if it touches the session DataFrame), and list it in the server instructions template. Counts are derived at runtime; do not hard-code them.
- Document it in `docs/guides/filaraki.md`. `tests/test_docs_tool_coverage.py` fails if a registered tool is missing there or from the MCP instructions.
- Add a `tests/test_filaraki_*.py` test.
- Mention it in the relevant skill under `src/filoma/skills/` and run `poe check-skills`.

### CLI and skills

- The CLI is Typer (`filoma.cli:cli`). `cli/_app.py` creates `app` and the sub-apps. `cli/__init__.py` imports each command module (`commands`, `filaraki`, `mcp`, `skills`, `watch`) purely so their decorators register. A new command module needs an import there.
- `src/filoma/skills/<name>/SKILL.md` are agent-side docs shipped in the wheel (maturin `include`). `BUNDLED_SKILLS` in `skills/__init__.py` must list each one. `filoma skills install --scope ...` copies them to where Claude Code, Copilot or Cursor expect them. `scripts/check_skills.py` fails if a skill references a CLI command, `flm.*` name or tool that no longer exists.

## Tests

`tests/` is flat, with subfolders `directories/`, `files/`, `images/` and `scripts/`. `asyncio_mode = "auto"`. Many tests build throwaway trees in `tempfile` directories rather than using fixtures on disk. Rust-dependent tests skip themselves when the extension is missing, so a green run without a build says nothing about the Rust engines. Tests must not depend on file order: never delete modules from `sys.modules` (this once left a second, empty `tool_registry` singleton that broke whichever test ran next).
