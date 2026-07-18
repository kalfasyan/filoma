"""Bundled agent skills shipped with filoma.

This subpackage ships ``SKILL.md`` directories that follow the
`Agent Skills <https://agentskills.io>`_ open standard, which is
recognized by GitHub Copilot (VS Code chat, Copilot CLI, and Copilot
coding agent, via ``.github/skills/<name>/SKILL.md``), Claude Code /
Claude Desktop, and other compatible agents.

The skills here are *agent-side knowledge* — they tell an LLM when and
how to invoke filoma's existing CLI / Python / MCP surfaces. They do
not contain any new code paths.

Contents:

- ``filoma-dataset-ci/`` — audit ML datasets for training readiness
- ``filoma-dedup/`` — duplicate / leakage detection
- ``filoma-explore/`` — directory exploration + DataFrame metadata
- ``templates/`` — snippets for ``AGENTS.md`` and Cursor ``.mdc`` rules

Use the ``filoma skills`` CLI to install them into the right place for
your agent (Claude Code, Claude Desktop, GitHub Copilot, Cursor, …).
"""

from __future__ import annotations

from importlib.resources import as_file, files
from pathlib import Path
from typing import Iterator, Tuple

# Skill directories that ship inside this package. Each entry is a folder
# containing a ``SKILL.md`` file. Update this list when adding new skills.
BUNDLED_SKILLS: tuple[str, ...] = (
    "filoma-dataset-ci",
    "filoma-dedup",
    "filoma-explore",
)


def iter_bundled_skills() -> Iterator[Tuple[str, Path]]:
    """Yield ``(skill_name, on_disk_path)`` for each bundled skill.

    The on-disk path is materialized via :func:`importlib.resources.as_file`
    so it works whether filoma is installed as a wheel, in editable mode,
    or vendored.
    """
    skills_root = files("filoma.skills")
    for name in BUNDLED_SKILLS:
        skill_resource = skills_root.joinpath(name)
        with as_file(skill_resource) as skill_path:
            yield name, Path(skill_path)


def get_template_path(template_name: str) -> Path:
    """Return the on-disk path to a bundled template file.

    Parameters
    ----------
    template_name:
        Filename inside ``filoma/skills/templates/`` (for example
        ``"AGENTS.md.tpl"`` or ``"cursor-rules.mdc.tpl"``).

    """
    template_resource = files("filoma.skills").joinpath("templates").joinpath(template_name)
    with as_file(template_resource) as template_path:
        return Path(template_path)
