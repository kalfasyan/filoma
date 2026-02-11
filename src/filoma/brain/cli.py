"""Brain CLI module for filoma."""

import asyncio
from typing import Optional

from loguru import logger
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt

from filoma.brain import get_agent
from filoma.brain.agent import FilomaDeps

console = Console()


async def run_chat_loop(model: Optional[str] = None):
    """Run an interactive chat loop with the Filoma Brain."""
    console.print(
        Panel(
            "[bold blue]🧠 Filoma Brain Chat[/bold blue]\n[dim]Ask anything about your filesystem. Type 'exit' or 'quit' to stop.[/dim]",
            border_style="blue",
        )
    )

    try:
        agent = get_agent(model=model)
        logger.info(f"Initialized agent with model: {agent.model}")
    except Exception as e:
        console.print(f"[red]Error initializing agent: {e}[/red]")
        return

    message_history = []
    deps = FilomaDeps()

    while True:
        try:
            user_input = Prompt.ask("\n[bold cyan]You[/bold cyan]")

            if user_input.lower() in ("exit", "quit", "bye"):
                console.print("[yellow]Goodbye! 👋[/yellow]")
                break

            if not user_input.strip():
                continue

            with console.status("[bold green]Brain is thinking...[/bold green]"):
                result = await agent.run(user_input, deps=deps, message_history=message_history)
                message_history = result.new_messages()

                # Robust extraction for pydantic-ai v1.58.0 RunResult
                # Try every known attribute for result text
                if hasattr(result, "data"):
                    response_text = str(result.data)
                elif hasattr(result, "output"):
                    # Some versions use .output
                    response_text = str(result.output)
                elif hasattr(result, "return_value"):
                    # Some use .return_value
                    response_text = str(result.return_value)
                else:
                    # Last resort: inspect the object attributes
                    # This helps debug what attributes ACTUALLY exist if we crash again
                    logger.debug(f"Available attributes on result object: {dir(result)}")
                    # Try to stringify the whole object if nothing else works, but clean it up
                    response_text = str(result)

            console.print("\n[bold magenta]Brain[/bold magenta]")
            console.print(Markdown(response_text))

        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted. Type 'exit' to quit.[/yellow]")
            continue
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            logger.debug(f"Full error details: {type(e).__name__}: {e}")


def chat(model: Optional[str] = None):
    """Entry point for the chat CLI command."""
    try:
        asyncio.run(run_chat_loop(model=model))
    except KeyboardInterrupt:
        pass
