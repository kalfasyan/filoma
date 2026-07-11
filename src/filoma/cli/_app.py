"""Typer app creation and shared state for the filoma CLI.

Imports of command modules in ``__init__.py`` trigger the
``@app.command()`` / ``@<sub>.command()`` decorators that register
each CLI entry point.
"""

import questionary  # noqa: F401 — used by interactive browser
import typer
from rich.console import Console

from filoma._version import __version__

app = typer.Typer(
    name="filoma",
    help="Interactive filesystem profiling and analysis tool",
    rich_markup_mode="rich",
    add_completion=False,
)


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        typer.echo(f"filoma {__version__}")
        raise typer.Exit()


@app.callback()
def main_callback(
    version: bool = typer.Option(False, "--version", help="Show version information", callback=version_callback),
) -> None:
    """Filoma - Interactive filesystem profiling and analysis tool."""
    return


filaraki_app = typer.Typer(
    name="filaraki",
    help="Intelligent filesystem analysis using AI",
    rich_markup_mode="rich",
)
app.add_typer(filaraki_app)

mcp_app = typer.Typer(
    name="mcp",
    help="MCP server for external agent integration",
    rich_markup_mode="rich",
)
app.add_typer(mcp_app)

skills_app = typer.Typer(
    name="skills",
    help="Install filoma agent skills (Claude Skills, Cursor rules, AGENTS.md)",
    rich_markup_mode="rich",
)
app.add_typer(skills_app)

console = Console()
