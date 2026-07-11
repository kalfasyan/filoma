"""Filoma CLI — :command:`filoma` entry point."""

from . import (
    commands,  # noqa: F401 — registers @app.command() decorators
    filaraki,  # noqa: F401 — registers @filaraki_app.command() decorators
    mcp,  # noqa: F401 — registers @mcp_app.command() decorators
    skills,  # noqa: F401 — registers @skills_app.command() decorators
    watch,  # noqa: F401 — registers @watch_app.command() decorators
)
from ._app import app


def cli() -> None:
    """Entry point for the filoma CLI (``pyproject.toml`` → ``filoma.cli:cli``)."""
    app()


__all__ = ["app", "cli"]
