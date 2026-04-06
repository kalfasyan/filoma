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
import os
import sys
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, AsyncIterator, List

from loguru import logger

from filoma.filaraki.agent import FilarakiDeps
from filoma.filaraki.tools import (
    analyze_image,
    assess_migration_readiness,
    audit_corrupted_files,
    audit_dataset,
    count_files,
    create_dataset_dataframe,
    dataframe_head,
    export_dataframe,
    filter_by_extension,
    filter_by_pattern,
    find_duplicates,
    generate_hygiene_report,
    get_directory_tree,
    get_file_info,
    list_available_tools,
    open_file,
    preview_image,
    probe_directory,
    read_file,
    search_files,
    sort_dataframe_by_size,
    summarize_dataframe,
)

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
    return [
        Tool(name=name, description=spec["description"], inputSchema=spec["inputSchema"])
        for name, spec in TOOL_SCHEMAS.items()
    ]


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
    """Execute a tool with the provided arguments."""
    deps = FilarakiDeps(working_dir=os.getcwd())
    ctx = _get_context(deps)

    mcp = _get_mcp_imports()
    TextContent = mcp["TextContent"]

    try:
        # DIRECTORY ANALYSIS
        if name == "count_files":
            result = count_files(ctx=ctx, path=arguments.get("path", "."))

        elif name == "probe_directory":
            result = probe_directory(
                ctx=ctx,
                path=arguments.get("path", "."),
                max_depth=arguments.get("max_depth"),
                ignore_safety_limits=arguments.get("ignore_safety_limits", False),
            )

        elif name == "get_directory_tree":
            result = get_directory_tree(ctx=ctx, path=arguments.get("path", "."))

        elif name == "find_duplicates":
            result = find_duplicates(
                ctx=ctx,
                path=arguments.get("path", "."),
                ignore_safety_limits=arguments.get("ignore_safety_limits", False),
            )

        # FILE OPERATIONS
        elif name == "get_file_info":
            result = get_file_info(ctx=ctx, path=arguments.get("path"))

        elif name == "search_files":
            result = search_files(
                ctx=ctx,
                path=arguments.get("path", "."),
                pattern=arguments.get("pattern"),
                extension=arguments.get("extension"),
                min_size=arguments.get("min_size"),
                max_depth=arguments.get("max_depth"),
                include_hidden=arguments.get("include_hidden", False),
                ignore_git_files=arguments.get("ignore_git_files", True),
            )
            _save_context(ctx)

        elif name == "open_file":
            result = open_file(ctx=ctx, path=arguments.get("path"))

        elif name == "read_file":
            result = read_file(
                ctx=ctx,
                path=arguments.get("path"),
                start_line=arguments.get("start_line", 1),
                end_line=arguments.get("end_line"),
            )

        # DATASET & DATAFRAME
        elif name == "create_dataset_dataframe":
            result = create_dataset_dataframe(
                ctx=ctx,
                path=arguments.get("path"),
                enrich=arguments.get("enrich", True),
            )
            _save_context(ctx)

        elif name == "filter_by_extension":
            result = filter_by_extension(ctx=ctx, extensions=arguments.get("extensions"))
            _save_context(ctx)

        elif name == "filter_by_pattern":
            result = filter_by_pattern(ctx=ctx, pattern=arguments.get("pattern"))
            _save_context(ctx)

        elif name == "sort_dataframe_by_size":
            result = sort_dataframe_by_size(
                ctx=ctx,
                ascending=arguments.get("ascending", False),
                top_n=arguments.get("top_n", 10),
            )
            _save_context(ctx)

        elif name == "dataframe_head":
            result = dataframe_head(ctx=ctx, n=arguments.get("n", 5))

        elif name == "summarize_dataframe":
            result = summarize_dataframe(ctx=ctx)

        elif name == "export_dataframe":
            result = export_dataframe(
                ctx=ctx,
                path=arguments.get("path"),
                format=arguments.get("format", "csv"),
            )

        # IMAGE ANALYSIS
        elif name == "analyze_image":
            result = analyze_image(ctx=ctx, path=arguments.get("path"))

        elif name == "preview_image":
            result = preview_image(
                ctx=ctx,
                path=arguments.get("path"),
                width=arguments.get("width", 60),
                mode=arguments.get("mode", "ansi"),
            )

        # DATA QUALITY
        elif name == "audit_corrupted_files":
            result = audit_corrupted_files(ctx=ctx, path=arguments.get("path"))

        elif name == "generate_hygiene_report":
            result = generate_hygiene_report(ctx=ctx, path=arguments.get("path"))

        elif name == "assess_migration_readiness":
            result = assess_migration_readiness(ctx=ctx, path=arguments.get("path"))

        elif name == "audit_dataset":
            result = audit_dataset(
                ctx=ctx,
                path=arguments.get("path"),
                mode=arguments.get("mode", "concise"),
                show_evidence=arguments.get("show_evidence", False),
                export_path=arguments.get("export_path"),
                export_format=arguments.get("export_format", "json"),
            )

        # UTILITIES
        elif name == "list_available_tools":
            result = list_available_tools(ctx=ctx)

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

        return [TextContent(type="text", text=result)]

    except Exception as e:
        logger.error(f"Error calling tool {name}: {e}")
        return [TextContent(type="text", text=f"Error executing {name}: {str(e)}")]


# Tool schemas for all MCP tools
TOOL_SCHEMAS = {
    "count_files": {
        "description": """Count total files and folders with FULL recursive scan.

Returns a complete count using fast Rust backend. Always scans entire directory tree.
Use this when user asks for total counts without filters.

Args:
    path: Directory path (e.g., '.' or '/home/user/data'). Supports ~ for home.

Returns: Report with total files, folders, and combined count.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to directory (e.g., '.' or '/home/user/data')",
                },
            },
            "required": ["path"],
        },
    },
    "probe_directory": {
        "description": """Probe directory and return summary with top extensions.

Useful for initial exploration. Shows top 10 extensions and metadata.
Has safety limits (depth=2) unless ignore_safety_limits=True.

Args:
    path: Directory path
    max_depth: Maximum recursion depth (null for unlimited)
    ignore_safety_limits: Allow deep scanning of large directories

Returns: Summary report with counts and extension breakdown.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to directory",
                },
                "max_depth": {
                    "type": ["integer", "null"],
                    "description": "Maximum recursion depth (null for unlimited)",
                    "default": None,
                },
                "ignore_safety_limits": {
                    "type": "boolean",
                    "description": "Allow deep scanning without safety limits",
                    "default": False,
                },
            },
            "required": ["path"],
        },
    },
    "get_directory_tree": {
        "description": """List immediate contents of a directory (non-recursive).

Shows files and folders with icons. Good for initial exploration.

Args:
    path: Directory path

Returns: List of contents with folder/file icons.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to directory",
                },
            },
            "required": ["path"],
        },
    },
    "get_file_info": {
        "description": """Get detailed metadata for a specific file.

Returns JSON with size, dates, type, and extended metadata.

Args:
    path: Path to file

Returns: JSON with file metadata.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to file",
                },
            },
            "required": ["path"],
        },
    },
    "search_files": {
        "description": r"""Search for files by pattern, extension, or size.

Automatically loads results into a DataFrame for further analysis.
Use for specific file type counts (e.g., 'count .py files').

Args:
    path: Directory to search
    pattern: Regex pattern for filenames (e.g., 'test_.*\.py$')
    extension: File extension without dot (e.g., 'py', 'jpg')
    min_size: Minimum size (e.g., '1M', '500K')
    max_depth: Maximum search depth
    include_hidden: Include hidden files (default: False)
    ignore_git_files: Respect .gitignore (default: True)

Returns: Search results with count and paths. Results stored in DataFrame.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory to search",
                    "default": ".",
                },
                "pattern": {
                    "type": ["string", "null"],
                    "description": "Regex pattern for filenames",
                    "default": None,
                },
                "extension": {
                    "type": ["string", "null"],
                    "description": "File extension without dot (e.g., 'py')",
                    "default": None,
                },
                "min_size": {
                    "type": ["string", "null"],
                    "description": "Minimum size (e.g., '1M', '500K')",
                    "default": None,
                },
                "max_depth": {
                    "type": ["integer", "null"],
                    "description": "Maximum search depth",
                    "default": None,
                },
                "include_hidden": {
                    "type": "boolean",
                    "description": "Include hidden files",
                    "default": False,
                },
                "ignore_git_files": {
                    "type": "boolean",
                    "description": "Respect .gitignore",
                    "default": True,
                },
            },
            "required": [],
        },
    },
    "find_duplicates": {
        "description": """Find duplicate files in a directory.

Groups duplicates and shows full paths. May apply safety limits.

Args:
    path: Directory to scan
    ignore_safety_limits: Allow scanning without limits

Returns: Report with duplicate groups and file counts.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory to scan",
                },
                "ignore_safety_limits": {
                    "type": "boolean",
                    "description": "Allow scanning without limits",
                    "default": False,
                },
            },
            "required": ["path"],
        },
    },
    "open_file": {
        "description": """Display file content directly to user's terminal.

Uses 'bat' (with syntax highlighting) or 'cat'. Most efficient for viewing.
The agent does NOT see the content - only the user sees it.

Args:
    path: Path to file

Returns: Confirmation that file was displayed.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to file to display",
                },
            },
            "required": ["path"],
        },
    },
    "read_file": {
        "description": """Read file content into agent context for analysis.

Use when you need to analyze/summarize/explain file content.
Returns text with line numbers in markdown code blocks.

Args:
    path: Path to file
    start_line: Line to start from (1-indexed, default: 1)
    end_line: Line to end at (inclusive, default: None for all)

Returns: File content with line numbers.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to file",
                },
                "start_line": {
                    "type": "integer",
                    "description": "Start line (1-indexed)",
                    "default": 1,
                },
                "end_line": {
                    "type": ["integer", "null"],
                    "description": "End line (inclusive, null for all)",
                    "default": None,
                },
            },
            "required": ["path"],
        },
    },
    "create_dataset_dataframe": {
        "description": """Create a metadata dataframe from all files in a directory.

Loads file metadata into a DataFrame for analysis.
After creation, use filter/sort/summarize tools.

Args:
    path: Dataset directory path
    enrich: Add extended metadata (default: True)

Returns: Confirmation with DataFrame info (rows, columns).""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Dataset directory path",
                },
                "enrich": {
                    "type": "boolean",
                    "description": "Add extended metadata (slower but more info)",
                    "default": True,
                },
            },
            "required": ["path"],
        },
    },
    "filter_by_extension": {
        "description": """Filter current DataFrame by file extension(s).

Requires an existing DataFrame (from search_files or create_dataset_dataframe).
Each filter updates the DataFrame - you can chain filters.

Args:
    extensions: Extension(s) to filter by. Can be string 'py,jpg' or list ['py', 'rs']

Returns: Confirmation with filtered count.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "extensions": {
                    "type": "string",
                    "description": "Extensions (e.g., 'py,jpg' or 'py')",
                },
            },
            "required": ["extensions"],
        },
    },
    "filter_by_pattern": {
        "description": r"""Filter current DataFrame by regex pattern.

Matches paths against regex pattern. Requires existing DataFrame.

Args:
    pattern: Regex pattern (e.g., 'train/.*\.jpg$' or 'test_')

Returns: Confirmation with filtered count.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regex pattern for path matching",
                },
            },
            "required": ["pattern"],
        },
    },
    "sort_dataframe_by_size": {
        "description": """Sort current DataFrame by file size.

Shows top N largest/smallest files. Requires existing DataFrame.

Args:
    ascending: Sort ascending (smallest first) (default: False)
    top_n: Number of results to show (default: 10, max: 100)

Returns: List of top files with sizes.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ascending": {
                    "type": "boolean",
                    "description": "Sort ascending (smallest first)",
                    "default": False,
                },
                "top_n": {
                    "type": "integer",
                    "description": "Number of results (max 100)",
                    "default": 10,
                },
            },
            "required": [],
        },
    },
    "dataframe_head": {
        "description": """Show first N rows of current DataFrame.

Useful after search/filter to see actual file paths. Requires existing DataFrame.

Args:
    n: Number of rows (default: 5, max: 200)

Returns: First N rows as formatted data.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "n": {
                    "type": "integer",
                    "description": "Number of rows (max 200)",
                    "default": 5,
                },
            },
            "required": [],
        },
    },
    "summarize_dataframe": {
        "description": """Get summary statistics of current DataFrame.

Shows total count, top extensions, top directories. Requires existing DataFrame.

Args: None

Returns: JSON summary with counts and breakdowns.""",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    "export_dataframe": {
        "description": """Export current DataFrame to file.

Requires existing DataFrame. Supported formats: csv, json, parquet.
This is the ONLY tool that writes files - all others are read-only.

Args:
    path: Output file path
    format: Export format - 'csv', 'json', or 'parquet' (default: csv)

Returns: Confirmation of successful export.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Output file path",
                },
                "format": {
                    "type": "string",
                    "description": "Export format: csv, json, or parquet",
                    "default": "csv",
                },
            },
            "required": ["path"],
        },
    },
    "analyze_image": {
        "description": """Analyze an image file for shape, dtype, and statistics.

Returns technical metadata about the image.

Args:
    path: Path to image file

Returns: JSON with shape, dtype, and basic stats.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to image file",
                },
            },
            "required": ["path"],
        },
    },
    "preview_image": {
        "description": """Generate a visual preview of an image.

Displays the image directly in user's terminal using ANSI color blocks or ASCII.

Args:
    path: Path to image file
    width: Preview width in characters (default: 60)
    mode: 'ansi' (colored) or 'ascii' (grayscale) (default: ansi)

Returns: Confirmation that preview was displayed.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to image file",
                },
                "width": {
                    "type": "integer",
                    "description": "Preview width in characters",
                    "default": 60,
                },
                "mode": {
                    "type": "string",
                    "description": "'ansi' (colored) or 'ascii' (grayscale)",
                    "default": "ansi",
                },
            },
            "required": ["path"],
        },
    },
    "audit_corrupted_files": {
        "description": """Audit for corrupted files, zero-byte files, and integrity issues.

Returns structured JSON report with findings, severity, and recommendations.
Useful for dataset validation before training or migration.

Args:
    path: Directory to audit

Returns: JSON audit report with corruption findings.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory to audit",
                },
            },
            "required": ["path"],
        },
    },
    "generate_hygiene_report": {
        "description": """Generate comprehensive dataset hygiene report.

Analyzes quality metrics: duplicates, class balance, cross-split leakage, anomalies.
Returns overall score (0-100) and actionable recommendations.

Args:
    path: Dataset directory

Returns: JSON hygiene report with metrics and issues.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Dataset directory",
                },
            },
            "required": ["path"],
        },
    },
    "assess_migration_readiness": {
        "description": """Assess dataset readiness for migration.

Evaluates: integrity, structure, blockers, risks.
Returns readiness score (0-100) and estimated effort.

Args:
    path: Dataset directory

Returns: JSON migration readiness report.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Dataset directory",
                },
            },
            "required": ["path"],
        },
    },
    "audit_dataset": {
        "description": """Run full dataset audit workflow in one call.

Executes corrupted-file audit, hygiene report, and migration readiness,
then returns one consolidated summary plus full component reports.

Args:
    path: Dataset directory
    mode: 'concise' (default) or 'verbose'
    show_evidence: Include sample duplicate/corruption evidence
    export_path: Optional path to write consolidated report
    export_format: 'json' (default), 'md', or 'html'

Returns: Consolidated workflow report with executive summary.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Dataset directory",
                },
                "mode": {
                    "type": "string",
                    "enum": ["concise", "verbose"],
                    "default": "concise",
                    "description": "Response verbosity mode",
                },
                "show_evidence": {
                    "type": "boolean",
                    "default": False,
                    "description": "Include sample evidence in response",
                },
                "export_path": {
                    "type": ["string", "null"],
                    "default": None,
                    "description": "Optional output path for report export",
                },
                "export_format": {
                    "type": "string",
                    "enum": ["json", "md", "html"],
                    "default": "json",
                    "description": "Export format when export_path is provided",
                },
            },
            "required": ["path"],
        },
    },
    "list_available_tools": {
        "description": """List all available tools and their descriptions.

Use this if you are unsure what operations are possible.

Args: None

Returns: Complete API reference with all available tools documented.""",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
}


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
