"""Smoke tests for the ``filoma skills`` CLI subcommand.

These tests exercise the bundled skill discovery + install flow end
to end, against an isolated temporary directory. They do not touch
the user's real ``~/.claude/skills`` location.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from filoma.cli import app
from filoma.skills import BUNDLED_SKILLS, iter_bundled_skills


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_bundled_skills_have_skill_md():
    """Every advertised bundled skill must have a SKILL.md on disk."""
    seen = set()
    for name, skill_dir in iter_bundled_skills():
        seen.add(name)
        skill_md = skill_dir / "SKILL.md"
        assert skill_md.exists(), f"{name} is missing SKILL.md at {skill_md}"
        body = skill_md.read_text(encoding="utf-8")
        assert body.startswith("---"), f"{name}: SKILL.md must start with YAML frontmatter"
        assert "name:" in body, f"{name}: missing 'name' frontmatter field"
        assert "description:" in body, f"{name}: missing 'description' frontmatter field"

    assert seen == set(BUNDLED_SKILLS), f"BUNDLED_SKILLS list out of sync: declared {set(BUNDLED_SKILLS)}, found {seen}"


def test_skills_list_command(runner: CliRunner):
    """`filoma skills list` should print every bundled skill name."""
    result = runner.invoke(app, ["skills", "list"])
    assert result.exit_code == 0, result.output
    for name in BUNDLED_SKILLS:
        assert name in result.output, f"Expected '{name}' in output:\n{result.output}"


def test_skills_where_command(runner: CliRunner):
    """`filoma skills where` should report a path for each known scope."""
    for scope in ("user", "project", "vscode"):
        result = runner.invoke(app, ["skills", "where", "--scope", scope])
        assert result.exit_code == 0, f"scope={scope}\n{result.output}"
        assert scope in result.output


def test_skills_where_rejects_unknown_scope(runner: CliRunner):
    result = runner.invoke(app, ["skills", "where", "--scope", "bogus"])
    assert result.exit_code != 0


def test_skills_install_project_scope(runner: CliRunner, tmp_path: Path, monkeypatch):
    """`filoma skills install` (default scope) copies skills to .claude/skills/."""
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["skills", "install"])
    assert result.exit_code == 0, result.output

    target_root = tmp_path / ".claude" / "skills"
    assert target_root.is_dir()

    for name in BUNDLED_SKILLS:
        skill_dir = target_root / name
        assert skill_dir.is_dir(), f"Expected {skill_dir} to exist"
        assert (skill_dir / "SKILL.md").is_file()


def test_skills_install_vscode_scope(runner: CliRunner, tmp_path: Path, monkeypatch):
    """`--scope vscode` writes to .github/skills/."""
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["skills", "install", "--scope", "vscode"])
    assert result.exit_code == 0, result.output

    target_root = tmp_path / ".github" / "skills"
    assert target_root.is_dir()
    for name in BUNDLED_SKILLS:
        assert (target_root / name / "SKILL.md").is_file()


def test_skills_install_single_by_name(runner: CliRunner, tmp_path: Path, monkeypatch):
    """`--name` installs only the requested skill."""
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["skills", "install", "--name", "filoma-dedup"])
    assert result.exit_code == 0, result.output

    target_root = tmp_path / ".claude" / "skills"
    assert (target_root / "filoma-dedup" / "SKILL.md").is_file()
    # The other skills should NOT have been installed
    for other in BUNDLED_SKILLS:
        if other == "filoma-dedup":
            continue
        assert not (target_root / other).exists(), f"Unexpected install of {other}"


def test_skills_install_unknown_name_errors(runner: CliRunner, tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["skills", "install", "--name", "does-not-exist"])
    assert result.exit_code != 0


def test_skills_install_skips_existing_without_force(runner: CliRunner, tmp_path: Path, monkeypatch):
    """Re-running install without --force preserves the existing skill folder."""
    monkeypatch.chdir(tmp_path)

    runner.invoke(app, ["skills", "install"])
    skill_md = tmp_path / ".claude" / "skills" / "filoma-explore" / "SKILL.md"
    assert skill_md.is_file()

    sentinel = "USER EDIT — SHOULD SURVIVE\n"
    skill_md.write_text(sentinel, encoding="utf-8")

    result = runner.invoke(app, ["skills", "install"])
    assert result.exit_code == 0
    assert skill_md.read_text(encoding="utf-8") == sentinel, "Install without --force must not overwrite"


def test_skills_install_force_overwrites(runner: CliRunner, tmp_path: Path, monkeypatch):
    """`--force` replaces the existing skill folder with the bundled version."""
    monkeypatch.chdir(tmp_path)

    runner.invoke(app, ["skills", "install"])
    skill_md = tmp_path / ".claude" / "skills" / "filoma-explore" / "SKILL.md"
    skill_md.write_text("user-edited", encoding="utf-8")

    result = runner.invoke(app, ["skills", "install", "--force"])
    assert result.exit_code == 0
    assert skill_md.read_text(encoding="utf-8").startswith("---"), "Force install should restore frontmatter"


def test_skills_agents_md_print(runner: CliRunner):
    """Without --write, agents-md prints the snippet."""
    result = runner.invoke(app, ["skills", "agents-md"])
    assert result.exit_code == 0
    assert "filoma" in result.output.lower()


def test_skills_agents_md_creates_file(runner: CliRunner, tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["skills", "agents-md", "--write"])
    assert result.exit_code == 0

    written = tmp_path / "AGENTS.md"
    assert written.is_file()
    body = written.read_text(encoding="utf-8")
    assert "filoma" in body.lower()


def test_skills_agents_md_appends_to_existing(runner: CliRunner, tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    existing = "# My project\n\nSome existing instructions.\n"
    (tmp_path / "AGENTS.md").write_text(existing, encoding="utf-8")

    result = runner.invoke(app, ["skills", "agents-md", "--write"])
    assert result.exit_code == 0

    body = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert body.startswith(existing.rstrip())
    assert "filoma" in body.lower()


def test_skills_agents_md_idempotent_when_already_mentions_filoma(runner: CliRunner, tmp_path: Path, monkeypatch):
    """Re-running --write is a no-op once the snippet is in place."""
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["skills", "agents-md", "--write"])
    body_before = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")

    result = runner.invoke(app, ["skills", "agents-md", "--write"])
    assert result.exit_code == 0
    body_after = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert body_before == body_after


def test_skills_cursor_rules_print(runner: CliRunner):
    result = runner.invoke(app, ["skills", "cursor-rules"])
    assert result.exit_code == 0
    assert "filoma" in result.output.lower()
    assert "alwaysApply" in result.output


def test_skills_cursor_rules_writes_file(runner: CliRunner, tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["skills", "cursor-rules", "--write"])
    assert result.exit_code == 0

    target = tmp_path / ".cursor" / "rules" / "filoma.mdc"
    assert target.is_file()
    body = target.read_text(encoding="utf-8")
    assert body.startswith("---")
    assert "filoma" in body.lower()


def test_skills_cursor_rules_does_not_clobber(runner: CliRunner, tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    target = tmp_path / ".cursor" / "rules" / "filoma.mdc"
    target.parent.mkdir(parents=True)
    target.write_text("user content", encoding="utf-8")

    result = runner.invoke(app, ["skills", "cursor-rules", "--write"])
    assert result.exit_code != 0
    assert target.read_text(encoding="utf-8") == "user content"
