# Contributing to filoma

Thanks for helping out. This page is the short human version; [AGENTS.md](AGENTS.md) has the full project layout and code conventions (it is written for coding agents but is just as useful to people).

## Set up

```bash
uv sync --extra dev --extra all     # or: pip install -e ".[dev,all]"
maturin develop --release           # builds the Rust extension (needs a Rust toolchain)
poe test                            # should be green before you change anything
```

The base install is intentionally small. The agent, RAG and pandas stacks live in optional extras (`agent`, `rag`, `pandas`), so contributors install `all`.

## Everyday commands

| Task                                     | Command                                        |
| ---------------------------------------- | ---------------------------------------------- |
| Run the tests (parallel, no API keys)    | `poe test`                                     |
| Run one test                             | `pytest tests/test_x.py::test_name -v`         |
| Lint / auto-fix / format                 | `poe lint` / `poe lint-fix` / `poe format-fix` |
| All pre-commit hooks (incl. Rust clippy) | `poe precommit`                                |
| Check bundled skills against the CLI     | `poe check-skills`                             |
| Benchmark the backends                   | `poe benchmark /path -n 3`                     |

Do not bypass pre-commit with `--no-verify`. CI runs the same hooks, the test suite on Python 3.11 to 3.14, and a separate job on a base install with no extras.

## Things that are easy to get wrong

- **Keep `import filoma` cheap.** Heavy dependencies (Polars, Pillow, pydantic-ai, mcp, lancedb, ...) are imported inside functions. `tests/test_lazy_imports.py` enforces this.
- **Optional extras stay optional.** Code and tests that need `agent`, `rag` or `pandas` must degrade cleanly: tests use `pytest.importorskip(...)` and user-facing errors say which extra to install. `tests/test_core_without_optional_extras.py` simulates a base install.
- **Scan engines must agree.** The Rust engines, the Python backend and fd share one contract (see "Engine harmonization contract" in `docs/reference/architecture.md`). `tests/test_engine_parity_generative.py` checks all of them against an `os.scandir` oracle on random trees. After editing `.rs` files, rebuild with `maturin develop --release`, because the tests only exercise the installed extension.
- **Tools are defined once**, in `src/filoma/filaraki/tools.py`, and shared by the agent and the MCP server. Adding one means registering it, deciding whether the MCP server exposes it, and documenting it in `docs/guides/filaraki.md` (a test checks this).
- **Docstrings** are required on public functions (pydocstyle via ruff), and line length is 210.

## Extending filoma

- **Add a tool from another package** without touching filoma: see [Writing a filoma plugin](docs/guides/plugins.md) and the working example in [examples/plugin_example](examples/plugin_example).
- **Add a scan backend**: follow the `fd` backend as the reference implementation (`docs/reference/architecture.md`).

## Pull requests

- Brief, present-tense title with no prefix.
- Reference the roadmap item when there is one (for example `ref docs/roadmap/adoption.md §2.1`).
- Run `poe lint` and `poe test` first.
- Keep the change to what the PR is about; the roadmap in `docs/roadmap/adoption.md` says what is in and out of scope.
