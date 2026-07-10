""":command:`filoma filaraki` — Filaraki agent chat."""

from typing import Optional

import typer

from ._app import filaraki_app


@filaraki_app.command("chat")
def filaraki_chat(
    model: Optional[str] = typer.Option(None, "--model", "-m", help="AI model to use"),
) -> None:
    """Start an interactive chat session with Filaraki."""
    from filoma.filaraki.cli import chat as start_chat

    start_chat(model=model)
