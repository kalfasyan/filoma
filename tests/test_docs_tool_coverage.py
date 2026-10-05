"""Guard against drift between the ToolRegistry and the places that describe it."""

from pathlib import Path

import pytest

import filoma.filaraki.tools  # noqa: F401 — triggers @tool_registry.register decorators
from filoma.tool_registry import tool_registry

_FILARAKI_GUIDE = Path(__file__).resolve().parent.parent / "docs" / "guides" / "filaraki.md"


def test_every_registered_tool_is_documented_in_filaraki_guide():
    """Each registered tool name must appear (in backticks) in docs/guides/filaraki.md."""
    if not _FILARAKI_GUIDE.exists():
        pytest.skip("docs/ not available (installed from sdist/wheel)")
    guide = _FILARAKI_GUIDE.read_text(encoding="utf-8")
    plugins = tool_registry.plugin_tool_names()  # third-party tools document themselves (see docs/guides/plugins.md)
    undocumented = sorted(spec.name for spec in tool_registry.list_specs() if spec.name not in plugins and f"`{spec.name}`" not in guide)
    assert not undocumented, f"Tools missing from docs/guides/filaraki.md: {undocumented}"


def test_every_mcp_tool_is_listed_in_server_instructions():
    """The hand-written MCP instructions must mention every exposed tool."""
    pytest.importorskip("mcp")
    from filoma.mcp_server import _MCP_TOOL_NAMES, _server_instructions

    text = _server_instructions()
    missing = sorted(name for name in _MCP_TOOL_NAMES if name not in text)
    assert not missing, f"Tools missing from MCP server instructions: {missing}"
    assert f"{len(_MCP_TOOL_NAMES)} filesystem analysis capabilities" in text
