"""MCP Server for Filoma - exposes filesystem analysis tools to external agents.

This module provides an MCP (Model Context Protocol) server that wraps filoma's
filaraki tools, making them accessible to any MCP-compatible client (nanobot
recommended).

Usage:
    # Run the MCP server
    uv run python -m filoma.mcp_server

    # Or via CLI (when installed)
    filoma mcp serve

Environment Variables:
    FILOMA_MCP_TRANSPORT: Transport type - 'stdio' (default) or 'sse'
    FILOMA_MCP_PORT: Port for SSE transport (default: 8000)

Configuration (nanobot):
    Add to ~/.nanobot/config.json under "mcpServers":
    {
      "mcpServers": {
        "filoma": {
          "command": "uv",
          "args": ["run", "--directory", "/path/to/filoma", "filoma", "mcp", "serve"]
        }
      }
    }
"""

import asyncio
import errno
import io
import os
import sys
from contextlib import asynccontextmanager, redirect_stdout
from typing import TYPE_CHECKING, Any, AsyncIterator, List

from loguru import logger

import filoma.filaraki.tools  # noqa: F401 — triggers @tool_registry.register decorators
from filoma.filaraki.agent import FilarakiDeps
from filoma.tool_registry import tool_registry

# Reconfigure loguru to write to stderr (required for MCP stdio transport)
# The MCP protocol uses stdout for JSON-RPC messages, so logs must go to stderr
logger.remove()  # Remove default handler
logger.add(sys.stderr)  # Add stderr handler

# Stub variables for type checking - we create a minimal stub class
if TYPE_CHECKING:
    pass


def _get_mcp_imports():
    """Import mcp modules only when the server actually starts."""
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import EmbeddedResource, ImageContent, TextContent, Tool

    return {
        "Server": Server,
        "stdio_server": stdio_server,
        "EmbeddedResource": EmbeddedResource,
        "ImageContent": ImageContent,
        "TextContent": TextContent,
        "Tool": Tool,
    }


class SimpleRunContext:
    """Simple context wrapper that mimics pydantic-ai RunContext for tool calls.

    Tools only access ctx.deps.current_df, so this minimal wrapper suffices.
    """

    def __init__(self, deps: FilarakiDeps):
        """Initialize the context with dependencies."""
        self.deps = deps


# Stateful storage for DataFrame operations across tool calls
_dataframe_state: dict = {}
# Application instance - created lazily
_app: Any = None


def _is_graceful_stdio_disconnect(exc: BaseException) -> bool:
    """Return True for expected stdio disconnect errors from MCP clients."""
    if isinstance(exc, BaseExceptionGroup):
        return all(_is_graceful_stdio_disconnect(sub_exc) for sub_exc in exc.exceptions)

    if isinstance(exc, (BrokenPipeError, ConnectionResetError, EOFError)):
        return True

    if isinstance(exc, OSError) and getattr(exc, "errno", None) == errno.EPIPE:
        return True

    return False


async def list_tools() -> List[Any]:
    """List all available tools exposed by this MCP server.

    NOTE: This is the module-level function used for testing without mcp import.
    The actual server uses the registered handlers inside _get_app().
    """
    mcp = _get_mcp_imports()
    Tool = mcp["Tool"]
    return [Tool(name=spec.name, description=spec.description, inputSchema=spec.param_schema) for spec in tool_registry.list_specs() if spec.name in _MCP_TOOL_NAMES]


async def call_tool(name: str, arguments: dict) -> List[Any]:
    """Execute a tool with the provided arguments.

    NOTE: This is the module-level function used for testing without mcp import.
    The actual server uses the registered handlers inside _get_app().
    """
    return await _call_tool_impl(name, arguments)


def _get_app() -> Any:
    """Get or create the MCP server instance lazily."""
    global _app
    if _app is None:
        mcp = _get_mcp_imports()
        Server = mcp["Server"]

        @asynccontextmanager
        async def app_lifespan(server: Any) -> AsyncIterator[FilarakiDeps]:
            """Manage application lifecycle with shared dependencies."""
            deps = FilarakiDeps(working_dir=os.getcwd())
            logger.info(f"Filoma MCP Server started. Working directory: {deps.working_dir}")
            try:
                yield deps
            finally:
                logger.info("Filoma MCP Server shutting down.")

        _app = Server(
            "filoma",
            instructions="""
Filoma MCP Server - Powerful filesystem analysis tools for AI agents.

This server provides 22 filesystem analysis capabilities organized into categories:

DIRECTORY ANALYSIS:
- count_files: Full recursive scan counting all files/folders
- probe_directory: Scan directory for summary statistics
- get_directory_tree: List immediate directory contents
- find_duplicates: Find duplicate files

FILE OPERATIONS:
- get_file_info: Detailed file metadata
- search_files: Search by pattern, extension, or size
- open_file: Display file to user's terminal
- read_file: Read file content for analysis

DATASET & DATAFRAME:
- create_dataset_dataframe: Create metadata dataframe from directory
- filter_by_extension: Filter dataframe by file extension
- filter_by_pattern: Filter dataframe by regex pattern
- sort_dataframe_by_size: Sort by file size
- dataframe_head: Show first N rows
- summarize_dataframe: Get summary statistics
- export_dataframe: Export to csv/json/parquet

IMAGE ANALYSIS:
- analyze_image: Get image shape, dtype, statistics
- preview_image: Generate visual preview (ANSI/ASCII)

DATA QUALITY:
- audit_corrupted_files: Find corrupted/zero-byte files
- generate_hygiene_report: Quality metrics and issues
- assess_migration_readiness: Dataset migration assessment
- audit_dataset: One-call dataset audit workflow (corruption + hygiene + readiness)

UTILITIES:
- list_available_tools: Show all available tools with descriptions

All tools support path expansion (~ for home directory) and validation.
""",
        )

        # Register the tool handlers with the Server instance
        _app.list_tools()(list_tools)
        _app.call_tool()(call_tool)

    return _app


def _get_context(deps: FilarakiDeps) -> SimpleRunContext:
    """Create a SimpleRunContext with current state."""
    # Restore DataFrame from state if exists
    if "current_df" in _dataframe_state:
        deps.current_df = _dataframe_state["current_df"]
    return SimpleRunContext(deps=deps)


def _save_context(ctx: SimpleRunContext) -> None:
    """Save DataFrame state after tool execution."""
    if ctx.deps.current_df is not None:
        _dataframe_state["current_df"] = ctx.deps.current_df


async def _call_tool_impl(name: str, arguments: dict) -> List[Any]:
    """Execute a tool with the provided arguments, using the ToolRegistry."""
    deps = FilarakiDeps(working_dir=os.getcwd())
    ctx = _get_context(deps)

    mcp = _get_mcp_imports()
    TextContent = mcp["TextContent"]

    def _run_guarded_stdout(func: Any, *args: Any, **kwargs: Any) -> Any:
        """Run a tool while capturing accidental stdout writes."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            result = func(*args, **kwargs)

        leaked = buf.getvalue()
        if leaked:
            preview = leaked[:300].replace("\n", "\\n")
            logger.warning(f"Suppressed non-JSON stdout from tool '{name}': {preview}")

        return result

    spec = tool_registry.get_spec(name)
    if spec is None:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    known_params = set(spec.param_schema.get("properties", {}).keys())
    filtered_args = {k: v for k, v in arguments.items() if k in known_params}

    try:
        result = _run_guarded_stdout(spec.callable, ctx=ctx, **filtered_args)

        if name in _DATAFRAME_TOOLS:
            _save_context(ctx)

        return [TextContent(type="text", text=result)]

    except Exception as e:
        logger.error(f"Error calling tool {name}: {e}")
        return [TextContent(type="text", text=f"Error executing {name}: {str(e)}")]


# Tool subsets for MCP exposure and DataFrame state tracking
_MCP_TOOL_NAMES = frozenset(
    {
        "count_files",
        "probe_directory",
        "get_directory_tree",
        "find_duplicates",
        "get_file_info",
        "search_files",
        "open_file",
        "read_file",
        "create_dataset_dataframe",
        "filter_by_extension",
        "filter_by_pattern",
        "sort_dataframe_by_size",
        "dataframe_head",
        "summarize_dataframe",
        "export_dataframe",
        "analyze_image",
        "preview_image",
        "audit_corrupted_files",
        "generate_hygiene_report",
        "assess_migration_readiness",
        "audit_dataset",
        "list_available_tools",
    }
)

_DATAFRAME_TOOLS = frozenset(
    {
        "search_files",
        "create_dataset_dataframe",
        "filter_by_extension",
        "filter_by_pattern",
        "sort_dataframe_by_size",
    }
)


async def main():
    """Run the MCP server with configured transport."""
    # Ensure the app is created (this imports mcp)
    app = _get_app()

    transport = os.getenv("FILOMA_MCP_TRANSPORT", "stdio")

    if transport == "stdio":
        # Signal tool layer to avoid direct stdout output (must remain JSON-RPC only).
        os.environ["FILOMA_MCP_STDIO"] = "1"
        mcp = _get_mcp_imports()
        stdio_server = mcp["stdio_server"]
        try:
            async with stdio_server() as (read_stream, write_stream):
                await app.run(
                    read_stream,
                    write_stream,
                    app.create_initialization_options(),
                )
        except BaseException as exc:
            # Some clients probe/terminate stdio quickly, which can raise
            # BrokenPipe/connection-reset errors during stream flush.
            if _is_graceful_stdio_disconnect(exc):
                logger.debug("MCP stdio client disconnected. Exiting gracefully.")
                return
            raise
    elif transport == "sse":
        logger.info("SSE transport not yet implemented. Use stdio for now.")
        raise NotImplementedError("SSE transport coming soon. Use FILOMA_MCP_TRANSPORT=stdio")
    else:
        raise ValueError(f"Unknown transport: {transport}. Use 'stdio' or 'sse'.")


if __name__ == "__main__":
    asyncio.run(main())
