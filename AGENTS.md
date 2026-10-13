# AGENTS.md — Filoma

Filoma is a fast multi-backend file/directory profiling library with
an agentic interface. The headline framing is **Dataset CI for ML —
folder → verified dataset → insights → agent, in one pipeline.**

This file is for AI coding agents (Codex, Cursor, Aider, Copilot
coding agent, Gemini CLI, Goose, Junie, Windsurf, etc.) working on
the filoma codebase itself. End-users of filoma get a different
agent-facing surface: see [`src/filoma/skills/`](src/filoma/skills/).

## Project layout

| Path                       | Purpose                                                               |
| -------------------------- | --------------------------------------------------------------------- |
| `src/filoma/`              | Python source. `import filoma` is intentionally cheap (lazy imports). |
| `src/*.rs`, `Cargo.toml`   | Rust backend, built via maturin.                                      |
| `src/filoma/filaraki/`     | pydantic-ai agent + its filesystem tools (`tools.py`).                |
| `src/filoma/mcp_server.py` | MCP server exposing an allowlisted subset of those tools.             |
| `src/filoma/skills/`       | Bundled SKILL.md directories shipped to other agents.                 |
| `tests/`                   | pytest suite (`-m integration` for tests needing API keys).           |
| `docs/`                    | mkdocs site published to filoma.readthedocs.io.                       |
| `docs/roadmap/adoption.md` | North-star roadmap. New work should map to a phase here.              |
| `benchmarks/`              | Backend performance comparisons.                                      |

## Build and test

```bash
# Install dev dependencies (uv preferred, pip works)
uv sync --extra dev --extra all            # or: pip install -e ".[dev,all]"
                                           # (base install is minimal; tests need the agent/rag/pandas extras)

# Build the Rust extension (release mode is fast enough for local dev)
maturin develop --release

# Test
poe test                                   # parallel, skips integration
pytest -n auto tests/                      # equivalent
pytest tests/test_<file>.py -v             # focused

# Lint and format
poe lint                                   # ruff check
poe lint-fix                               # ruff check --fix
poe format-fix                             # ruff format

# Docs
mkdocs serve
```

## Code conventions

- **Lazy imports for heavy deps** (Polars, Pillow, pydantic-ai, mcp,
  pandas). The lazy-import regression test in
  `tests/test_lazy_imports.py` will catch eager imports — do not
  break it.
- **Backend selection** follows the Rust → fd → Python fallback.
  Don't introduce a fourth path; extend the existing abstraction.
  See `docs/reference/architecture.md`.
- **Traversal semantics are harmonized across engines** (symlinks not
  counted when `follow_links=False`, `max_depth`, empty-dir, and
  DataFrame-row semantics — see the "Engine harmonization contract"
  in `docs/reference/architecture.md`). When changing any engine
  (`src/dua_scan.rs`, `src/lib.rs`, `src/async_scan.rs`, the Python
  backend), keep the others in parity and extend the parity tests in
  `tests/test_rust_dua_core.py`. `tests/test_engine_parity_generative.py`
  checks every engine against an `os.scandir` oracle on random trees and is
  the authority on the contract; it must stay green. After editing `.rs`
  files, rebuild with `maturin develop --release` from your activated
  venv — the tests only exercise the extension that is installed. (A bare
  `cargo build` may link against a different Python than your venv's and
  produce an unloadable `.so`.)
- **Tools are defined once** in `src/filoma/filaraki/tools.py` via
  `@tool_registry.register` (`src/filoma/tool_registry.py`). The Filaraki
  agent consumes every registered tool; `mcp_server.py` exposes the
  `_MCP_TOOL_NAMES` allowlist (and `_DATAFRAME_TOOLS` marks those that
  read/write the per-session DataFrame). To add a tool: register it,
  add it to `_MCP_TOOL_NAMES` if it should be exposed over MCP, list it
  in the MCP server instructions and `docs/guides/filaraki.md`
  (`tests/test_docs_tool_coverage.py` enforces both), and add a matching
  entry under `src/filoma/skills/` if it is user-facing. Tool counts are
  derived at runtime; don't hard-code them.
- **Public API additions** flow through `src/filoma/__init__.py`'s
  lazy `__getattr__`. Do not eagerly import.
- **Docstrings** are required on public functions; ruff enforces
  pydocstyle (D rules, `D203`/`D213` ignored).
- **Line length is 210** to accommodate Rich UI strings — but please
  keep new code well under that.
- **No emojis in code or test output.** Rich panels in the CLI use
  decorative emojis sparingly; tests should be plain.

## Testing instructions

- Default test invocation: `poe test`.
- Integration tests live under the `integration` marker and need
  real provider keys (`MISTRAL_API_KEY`, `GEMINI_API_KEY`,
  `OPENAI_API_KEY`, or a running Ollama). They're skipped in CI.
- After editing `mcp_server.py`, run `tests/test_mcp_server.py` to
  catch tool-registration regressions.
- After editing any `filaraki/tools.py` tool, mirror with a test
  in `tests/test_filaraki_*.py`.
- Lazy-import regression: `pytest tests/test_lazy_imports.py` —
  must always pass.
- Demo smoke test: `pytest tests/test_cli_demo.py` — touches the full
  pipeline end-to-end on a tiny fixture.

## PR conventions

- Title: brief, present tense, no prefix.
- Reference roadmap items by section number when applicable, e.g.
  `ref docs/roadmap/adoption.md §2.1`.
- Run `poe lint` and `poe test` before pushing.
- Don't bypass `pre-commit` (`--no-verify` is forbidden).
- Don't add features outside the user's request — see the roadmap
  for what's in vs. out of scope.

## Filoma's own agent surfaces

When testing changes locally, exercise all three surfaces:

```bash
# 1. Direct Python API
python -c "import filoma as flm; flm.probe('.').print_summary()"

# 2. CLI / chat
filoma demo
filoma ask "how many python files in src/"

# 3. MCP server (stdio)
filoma mcp serve  # connect from any MCP client

# 4. Bundled skills (the agent-facing artifacts shipped in the wheel)
filoma skills list
filoma skills install --scope project
```

`.vscode/mcp.json` and `.mcp.json` (repo root) both point VS Code chat
and Copilot CLI respectively at the local dev build (`uv run --directory
. --extra agent filoma mcp serve`), scoped to this workspace only — they don't touch
your personal `~/.copilot/mcp-config.json` or global VS Code MCP config,
which are separate, user-scoped, and shared across every repo you open.
Run `copilot mcp list --json` from the repo root to confirm the workspace
entry (`filoma-dev`) is picked up alongside any personal servers you've
configured elsewhere.

> ⚠️ **`filoma` vs `filoma-dev` — these are two different processes with
> two different codebases**, and it's easy to silently call the wrong one:
>
> - `filoma-dev` (workspace-scoped, from `.mcp.json`/`.vscode/mcp.json`)
>   runs `uv run --directory . --extra agent filoma mcp serve` — this exact working
>   tree, including uncommitted local changes. Any tool/param you just
>   added or fixed here is only available through this one.
> - `filoma` (user-scoped, e.g. via `copilot mcp add filoma -- uvx -p 3.11
--from "filoma[agent]" filoma mcp serve`) runs the **published PyPI package** in an isolated
>   `uvx` environment — a separate process, frozen at whatever version was
>   last released, unaffected by anything in this working tree until a new
>   version is published.
>
> If both are configured (common for contributors who also followed the
> "Use with GitHub Copilot" README instructions in some other repo), an
> agent choosing between two identically-shaped tools can pick either one
> per call, with no visible indication of which — a fix made here can
> appear to silently "not work" because the call actually went to the
> stale published `filoma`. To verify which one served a call, diff the
> tool's description via `list_available_tools` between the two servers,
> or temporarily `copilot mcp remove filoma` while iterating on unreleased
> changes.

A change is only "done" when none of these are broken.
