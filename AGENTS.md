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
| `src/filoma/filaraki/`     | pydantic-ai agent + the 22 filesystem tools.                          |
| `src/filoma/mcp_server.py` | MCP server exposing the same 22 tools.                                |
| `src/filoma/skills/`       | Bundled SKILL.md directories shipped to other agents.                 |
| `tests/`                   | pytest suite (`-m integration` for tests needing API keys).           |
| `docs/`                    | mkdocs site published to filoma.readthedocs.io.                       |
| `docs/roadmap/adoption.md` | North-star roadmap. New work should map to a phase here.              |
| `benchmarks/`              | Backend performance comparisons.                                      |

## Build and test

```bash
# Install dev dependencies (uv preferred, pip works)
uv sync                                    # or: pip install -e ".[dev]"

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
- **Tool definitions are duplicated** today across
  `src/filoma/filaraki/tools.py` and `src/filoma/mcp_server.py`. The
  Phase 2 roadmap consolidates these into one `ToolRegistry`. Until
  then, edit both — and add a corresponding entry under
  `src/filoma/skills/` if the tool is user-facing.
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

A change is only "done" when none of these are broken.
