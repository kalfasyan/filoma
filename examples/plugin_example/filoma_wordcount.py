"""Example filoma plugin: adds a ``count_words`` tool to the Filaraki agent and the MCP server.

Install it next to filoma (``pip install -e examples/plugin_example``) and the tool
appears in ``flm.ask(...)``, ``filoma chat`` and ``filoma mcp serve`` with no other
configuration. See ``docs/guides/plugins.md``.
"""

from pathlib import Path
from typing import Any, Optional


def register(registry: Optional[Any] = None) -> None:
    """Entry point: register this plugin's tools with filoma's ``ToolRegistry``.

    filoma calls this once, lazily, the first time the tool list is needed, so keep
    it cheap: no filesystem I/O and no heavy imports at load time (import inside the
    tool body instead). ``registry`` exists only so tests can pass a fresh registry.
    """
    if registry is None:
        from filoma.tool_registry import tool_registry as registry

    try:
        from pydantic_ai import RunContext
    except ImportError:
        # Without the "agent" extra neither the agent nor the MCP server can run, so
        # there is nothing to register the tool with.
        return

    @registry.register
    def count_words(ctx: RunContext[Any], path: str, max_bytes: int = 1_000_000) -> str:
        """Count the words in a text file.

        Args:
            ctx: The run context (injected by filoma; not shown to the model).
            path: Path to a text file.
            max_bytes: Read at most this many bytes, to keep the tool cheap on huge files.

        """
        file_path = Path(path).expanduser().resolve()
        if not file_path.is_file():
            return f"Error: '{path}' is not a file."
        with file_path.open("rb") as handle:
            text = handle.read(max_bytes).decode("utf-8", errors="replace")
        return f"{file_path.name}: {len(text.split())} words"
