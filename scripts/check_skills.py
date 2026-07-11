#!/usr/bin/env python3
"""Validate that CLI commands and Python APIs referenced in bundled skills still exist.

Scans every ``src/filoma/skills/*/SKILL.md`` for:

- **CLI commands**: ``filoma <subcommand>`` in bash code blocks
- **Python APIs**: ``flm.<name>`` and ``from filoma.filaraki.tools import <name>``
  in Python code blocks

Each reference is validated against the current codebase:
  - CLI commands  →  Typer app command tree (``filoma.cli.app``)
  - Python helpers →  ``filoma.__all__``
  - Tool functions  →  ``ToolRegistry`` entries

Exit 0 on success, 1 on any broken reference.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"

# Forward references: commands/APIs documented in skills but scheduled for
# future roadmap phases. Remove entries once the feature ships.
# See docs/roadmap/adoption.md for phase descriptions.
FORWARD_REFERENCES: set[str] = set()


def main() -> int:
    """Entry point — return 0 on success, 1 if stale references found."""
    errors: list[str] = []

    # ------------------------------------------------------------------
    # 1. Walk CLI command tree (Typer app)
    # ------------------------------------------------------------------
    valid_cli_commands = _get_valid_cli_commands()

    # ------------------------------------------------------------------
    # 2. Collect valid Python references
    # ------------------------------------------------------------------
    valid_python = _get_valid_python_refs()

    # ------------------------------------------------------------------
    # 3. Scan each SKILL.md
    # ------------------------------------------------------------------
    skills_dir = SRC / "filoma" / "skills"
    for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
        skill_name = skill_md.parent.name
        text = skill_md.read_text(encoding="utf-8")

        refs = _extract_references(text)

        for ref in refs:
            if ref in FORWARD_REFERENCES:
                continue
            if ref.startswith("filoma "):
                cmd = ref.split(" ", 1)[1]  # strip "filoma "
                if cmd not in valid_cli_commands:
                    errors.append(f"{skill_name}: CLI command 'filoma {cmd}' not found")
            elif ref.startswith("flm."):
                name = ref.split(".", 1)[1].split("(")[0].strip()  # strip method call parens
                if name not in valid_python:
                    errors.append(f"{skill_name}: Python API 'flm.{name}' not found")
            elif ref.startswith("from filoma.filaraki.tools import"):
                tool_name = ref.rsplit("import ", 1)[1].strip()
                if tool_name not in valid_python:
                    errors.append(f"{skill_name}: Tool '{tool_name}' not in ToolRegistry")

    if errors:
        print("Skills drift detected — the following references are stale:\n")
        for err in errors:
            print(f"  [FAIL] {err}")
        print(f"\n{len(errors)} broken reference(s) found.")
        return 1

    print(f"Skills drift check passed — all references in {sum(1 for _ in skills_dir.glob('*/SKILL.md'))} SKILL.md files are valid.")
    return 0


# ====================================================================
# Internal helpers
# ====================================================================


def _get_valid_cli_commands() -> set[str]:
    """Collect all registered CLI subcommands from the Typer app."""
    from filoma.cli import app

    commands: set[str] = set()
    _walk_typer_app(app, commands)
    return commands


def _walk_typer_app(app: object, commands: set[str]) -> None:
    """Recursively walk a Typer app and its sub-apps to collect command names."""
    for cmd_info in getattr(app, "registered_commands", []):
        if cmd_info.name is not None:
            commands.add(cmd_info.name)
        elif cmd_info.callback is not None:
            # Fall back to the function name when Typer stores None as name
            commands.add(cmd_info.callback.__name__)
    for group in getattr(app, "registered_groups", []):
        _walk_typer_app(group.typer_instance, commands)


def _get_valid_python_refs() -> set[str]:
    """Collect all valid Python API references for the skills drift check."""
    import filoma

    # Trigger tool registration before querying the registry
    import filoma.filaraki.tools  # noqa: F401

    valid: set[str] = set()

    # Top-level __all__ entries
    valid.update(filoma.__all__)

    # ToolRegistry entries (tool function names)
    try:
        from filoma.tool_registry import tool_registry
    except Exception:
        pass
    else:
        for spec in tool_registry.list_specs():
            valid.add(spec.name)

    return valid


def _extract_references(text: str) -> list[str]:
    """Extract code references from a SKILL.md file.

    Returns a list of references like 'filoma demo', 'flm.Pipeline',
    'from filoma.filaraki.tools import audit_dataset'.
    """
    refs: list[str] = []

    # Extract fenced code blocks (```bash ... ``` and ```python ... ```)
    # Pattern: ```language\n...\n```
    code_blocks = re.findall(r"```(?:bash|python|sh)\s*\n(.*?)```", text, re.DOTALL)

    for block in code_blocks:
        for line in block.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            # CLI commands: `filoma <cmd>`
            m = re.match(r"filoma\s+(\S[\S ]*)", line)
            if m:
                cmd_str = m.group(1).strip()
                # Take only the first token as the subcommand, stripping <arg> placeholders
                subcmd = cmd_str.split()[0]
                refs.append(f"filoma {subcmd}")

            # Python: `flm.<name>(...)`
            m = re.match(r"flm\.(\w+)", line)
            if m:
                name = m.group(1)
                refs.append(f"flm.{name}")

            # Python: `from filoma.filaraki.tools import <name>`
            m = re.match(r"from\s+filoma\.filaraki\.tools\s+import\s+(\w+)", line)
            if m:
                refs.append(f"from filoma.filaraki.tools import {m.group(1)}")

    return refs


if __name__ == "__main__":
    sys.exit(main())
