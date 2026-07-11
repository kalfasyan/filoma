""":command:`filoma mcp` — MCP server for external agent integration."""

from ._app import console, mcp_app


@mcp_app.command("serve")
def mcp_serve() -> None:
    r"""Start the MCP server for external agent integration.

    This command starts a Model Context Protocol (MCP) server that exposes
    filoma's filesystem analysis tools to any MCP-compatible client.

    The server runs on stdio transport by default, making it compatible with
    nanobot and other MCP clients.

    Example:
        filoma mcp serve

    Environment variables:
        FILOMA_MCP_TRANSPORT: 'stdio' (default) or 'sse'
        FILOMA_MCP_PORT: Port for SSE transport (default: 8000)

    """
    import asyncio
    import os

    from filoma.mcp_server import main

    transport = os.getenv("FILOMA_MCP_TRANSPORT", "stdio")

    if transport != "stdio":
        console.print("[bold blue]Starting Filoma MCP Server...[/bold blue]")
        console.print("[dim]Server will run until interrupted (Ctrl+C)[/dim]\n")

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        if transport != "stdio":
            console.print("\n[yellow]MCP server stopped.[/yellow]")
