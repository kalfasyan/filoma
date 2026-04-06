"""Filaraki CLI module for filoma."""

import asyncio
import json
from typing import Optional

from loguru import logger
from pydantic_ai.messages import ModelResponse, TextPart
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt

from filoma.filaraki import get_agent
from filoma.filaraki.agent import FilarakiDeps

console = Console()


async def run_chat_loop(model: Optional[str] = None):
    """Run an interactive chat loop with Filaraki."""
    console.print(
        Panel(
            "[bold green]🌿 Filaraki Chat[/bold green]\n[dim]Ask anything about your filesystem. Type 'exit' or 'quit' to stop.[/dim]",
            border_style="green",
        )
    )

    try:
        agent = get_agent(model=model)
        logger.info(f"Initialized agent with model: {agent.model}")
    except Exception as e:
        console.print(f"[red]Error initializing agent: {e}[/red]")
        return

    message_history = []
    deps = FilarakiDeps()

    while True:
        try:
            user_input = Prompt.ask("\n[bold cyan]You[/bold cyan]")

            if user_input.lower() in ("exit", "quit", "bye"):
                console.print("[yellow]Goodbye! 👋[/yellow]")
                break

            if not user_input.strip():
                continue

            with console.status("[bold green]Filaraki is thinking...[/bold green]"):
                result = await agent.run(user_input, deps=deps, message_history=message_history)
                message_history = result.new_messages()

                # Extract the final text response from pydantic-ai v1.58.0 AgentRunResult
                # Use result.output as the primary source (pydantic-ai handles extraction)
                response_text = str(result.output) if result.output else None

                # If result.output is empty or None, manually extract from messages
                if not response_text or response_text == "None":
                    for msg in reversed(result.all_messages()):
                        if isinstance(msg, ModelResponse):
                            for part in msg.parts:
                                if isinstance(part, TextPart):
                                    response_text = part.content
                                    break
                        if response_text:
                            break

                # Final fallback
                if not response_text:
                    response_text = "No response"

                # Check if response is JSON-as-text (a known issue with some model generations)
                # This happens when the model outputs tool call parameters as text instead of making actual tool calls
                response_stripped = response_text.strip()

                # Handle cases where model adds prefixes like <|python_tag|> before JSON
                json_start = response_stripped.find("{")
                json_end = response_stripped.rfind("}")

                if json_start >= 0 and json_end > json_start:
                    potential_json = response_stripped[json_start : json_end + 1]

                    # Try to fix Python syntax (None, True, False) to JSON (null, true, false)
                    json_fixed = potential_json.replace(": None", ": null")
                    json_fixed = json_fixed.replace(": True", ": true")
                    json_fixed = json_fixed.replace(": False", ": false")

                    try:
                        parsed = json.loads(json_fixed)
                        if isinstance(parsed, dict) and "name" in parsed and "parameters" in parsed:
                            tool_name = parsed["name"]
                            logger.warning(f"Agent generated tool call as text instead of executing: {tool_name}")
                            console.print("\n[bold magenta]Filaraki[/bold magenta]")
                            console.print(
                                f"[yellow]⚠️  The model tried to call '{tool_name}' but generated text instead of executing the tool.[/yellow]"
                            )
                            console.print("[dim]This is a known issue with some models. Try rephrasing your question or being more specific.[/dim]")
                            continue
                    except (json.JSONDecodeError, ValueError, KeyError):
                        # Not a tool call JSON, treat as normal response
                        pass

            console.print("\n[bold magenta]Filaraki[/bold magenta]")
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
