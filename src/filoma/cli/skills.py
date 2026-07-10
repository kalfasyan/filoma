""":command:`filoma skills` — install filoma's bundled agent skills."""

from pathlib import Path
from typing import Optional

import typer
from rich.table import Table

from ._app import console, skills_app

_SKILL_SCOPES: dict[str, tuple[str, str]] = {
    "user": ("~/.claude/skills", "Personal Claude Code / Claude Desktop skills"),
    "project": (".claude/skills", "Project-local Claude Code skills"),
    "vscode": (".github/skills", "VS Code chat customization skills"),
}


def _resolve_scope_dir(scope: str) -> Path:
    """Translate a scope name into an absolute install directory."""
    if scope not in _SKILL_SCOPES:
        valid = ", ".join(sorted(_SKILL_SCOPES))
        raise typer.BadParameter(f"Unknown scope '{scope}'. Choose one of: {valid}")
    rel, _ = _SKILL_SCOPES[scope]
    return Path(rel).expanduser().resolve()


def _extract_skill_description(skill_md_path: Path) -> Optional[str]:
    """Pull ``description`` from the YAML frontmatter of a SKILL.md.

    Avoids a YAML dependency by doing a minimal text scan, since the
    field is always single-line in our bundled skills.
    """
    try:
        text = skill_md_path.read_text(encoding="utf-8")
    except OSError:
        return None
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    front = text[3:end]
    for line in front.splitlines():
        line = line.strip()
        if line.startswith("description:"):
            return line.split(":", 1)[1].strip().strip('"').strip("'")
    return None


@skills_app.command("list")
def skills_list() -> None:
    """List bundled filoma skills with their descriptions.

    Reads the YAML frontmatter from each bundled SKILL.md and shows a
    summary table.
    """
    from filoma.skills import iter_bundled_skills

    table = Table(show_header=True, header_style="bold blue")
    table.add_column("Skill", style="cyan", no_wrap=True)
    table.add_column("Description")

    for name, skill_dir in iter_bundled_skills():
        skill_md = skill_dir / "SKILL.md"
        description = "(missing SKILL.md)"
        if skill_md.exists():
            description = _extract_skill_description(skill_md) or "(no description)"
        if len(description) > 140:
            description = description[:137] + "..."
        table.add_row(name, description)

    console.print(table)


@skills_app.command("where")
def skills_where(
    scope: str = typer.Option(
        "project",
        "--scope",
        "-s",
        help="Where to install: 'user', 'project', or 'vscode'",
    ),
) -> None:
    """Show the install directory for a given scope without writing anything."""
    target = _resolve_scope_dir(scope)
    _, description = _SKILL_SCOPES[scope]
    console.print(f"[bold blue]Scope:[/bold blue] {scope}")
    console.print(f"[bold blue]Path:[/bold blue]  {target}")
    console.print(f"[dim]{description}[/dim]")


@skills_app.command("install")
def skills_install(
    scope: str = typer.Option(
        "project",
        "--scope",
        "-s",
        help="Where to install: 'user' (~/.claude/skills), 'project' (.claude/skills), or 'vscode' (.github/skills)",
    ),
    name: Optional[str] = typer.Option(
        None,
        "--name",
        "-n",
        help="Install only this skill by name. Defaults to all bundled skills.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Overwrite existing skill folders at the destination.",
    ),
) -> None:
    """Install bundled filoma skills into the chosen agent's skill directory.

    Examples:
        filoma skills install                   # → ./.claude/skills/
        filoma skills install --scope user      # → ~/.claude/skills/
        filoma skills install --scope vscode    # → ./.github/skills/
        filoma skills install -n filoma-dedup   # only install one skill

    """
    import shutil

    from filoma.skills import iter_bundled_skills

    target_root = _resolve_scope_dir(scope)
    target_root.mkdir(parents=True, exist_ok=True)

    skills_to_install = []
    for skill_name, skill_dir in iter_bundled_skills():
        if name is not None and skill_name != name:
            continue
        skills_to_install.append((skill_name, skill_dir))

    if not skills_to_install:
        if name is not None:
            console.print(f"[red]No bundled skill named '{name}'.[/red] Run [bold]filoma skills list[/bold] to see available skills.")
            raise typer.Exit(1)
        console.print("[yellow]No bundled skills found.[/yellow]")
        raise typer.Exit(1)

    installed = 0
    skipped = 0
    for skill_name, skill_dir in skills_to_install:
        dest = target_root / skill_name
        if dest.exists():
            if not force:
                console.print(f"[yellow]\u2298[/yellow] {skill_name} \u2192 already at {dest} (use --force to overwrite)")
                skipped += 1
                continue
            shutil.rmtree(dest)
        shutil.copytree(skill_dir, dest)
        console.print(f"[green]\u2713[/green] {skill_name} \u2192 {dest}")
        installed += 1

    console.print()
    console.print(f"[bold green]Installed {installed} skill(s)[/bold green]" + (f", skipped {skipped}" if skipped else "") + ".")
    if scope in ("user", "project"):
        console.print("[dim]Restart Claude Code to pick up new skills, or reload the skill list in your client.[/dim]")
    elif scope == "vscode":
        console.print("[dim]VS Code chat will discover the skills automatically when you re-open the workspace.[/dim]")


@skills_app.command("agents-md")
def skills_agents_md(
    write: bool = typer.Option(
        False,
        "--write",
        "-w",
        help="Append the snippet to AGENTS.md in the current directory (or create it).",
    ),
) -> None:
    """Print or append a filoma section to AGENTS.md.

    The AGENTS.md format is the open standard supported by OpenAI Codex,
    Cursor, Aider, Gemini CLI, Goose, the GitHub Copilot coding agent,
    and many others. This snippet teaches them how to drive filoma.
    """
    from filoma.skills import get_template_path

    snippet = get_template_path("AGENTS.md.tpl").read_text(encoding="utf-8")

    if not write:
        console.print(snippet, markup=False, highlight=False)
        return

    target = Path("AGENTS.md")
    if target.exists():
        existing = target.read_text(encoding="utf-8")
        if "filoma" in existing.lower():
            console.print("[yellow]AGENTS.md already mentions filoma \u2014 leaving it alone.[/yellow]")
            console.print("[dim]Edit it manually if you want to refresh the snippet.[/dim]")
            raise typer.Exit(0)
        joined = existing.rstrip() + "\n\n" + snippet
        target.write_text(joined, encoding="utf-8")
        console.print(f"[green]\u2713[/green] Appended filoma section to {target.resolve()}")
    else:
        target.write_text(snippet, encoding="utf-8")
        console.print(f"[green]\u2713[/green] Created {target.resolve()}")


@skills_app.command("cursor-rules")
def skills_cursor_rules(
    write: bool = typer.Option(
        False,
        "--write",
        "-w",
        help="Write the rule to .cursor/rules/filoma.mdc in the current directory.",
    ),
) -> None:
    """Print or write a Cursor rule (.mdc) for filoma.

    Cursor reads rules from ``.cursor/rules/*.mdc`` with YAML frontmatter
    controlling when they apply. The bundled rule auto-attaches based on
    description matching.
    """
    from filoma.skills import get_template_path

    rule = get_template_path("cursor-rules.mdc.tpl").read_text(encoding="utf-8")

    if not write:
        console.print(rule, markup=False, highlight=False)
        return

    rules_dir = Path(".cursor/rules")
    rules_dir.mkdir(parents=True, exist_ok=True)
    target = rules_dir / "filoma.mdc"
    if target.exists():
        console.print(f"[yellow]{target} already exists \u2014 use --force... actually, just delete it and re-run.[/yellow]")
        raise typer.Exit(1)
    target.write_text(rule, encoding="utf-8")
    console.print(f"[green]\u2713[/green] Wrote {target.resolve()}")
    console.print("[dim]Cursor picks up rules automatically; no reload needed.[/dim]")
