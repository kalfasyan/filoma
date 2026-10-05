import sys
from unittest.mock import MagicMock

import pytest

import filoma.tool_registry


@pytest.fixture
def fresh_registry():
    registry = filoma.tool_registry.ToolRegistry()
    return registry


def test_discover_plugins_is_idempotent(fresh_registry, monkeypatch):
    assert not fresh_registry._plugins_loaded

    call_count = 0

    def fake_entry_points(group):
        nonlocal call_count
        call_count += 1
        return []

    monkeypatch.setattr("importlib.metadata.entry_points", fake_entry_points)

    fresh_registry._discover_plugins()
    assert call_count == 1
    assert fresh_registry._plugins_loaded

    fresh_registry._discover_plugins()
    assert call_count == 1


def test_list_specs_triggers_discovery(fresh_registry):
    called = []

    def _fake_discover():
        called.append(True)

    fresh_registry._discover_plugins = _fake_discover
    _ = fresh_registry.list_specs()
    assert called == [True]


def test_get_spec_triggers_discovery(fresh_registry):
    called = []

    def _fake_discover():
        called.append(True)

    fresh_registry._discover_plugins = _fake_discover
    _ = fresh_registry.get_spec("nonexistent")
    assert called == [True]


def test_entry_point_registers_tool(fresh_registry, monkeypatch):
    def plugin_loader():
        fresh_registry.register(plugin_loader)

    fake_ep = MagicMock()
    fake_ep.load.return_value = plugin_loader

    monkeypatch.setattr("importlib.metadata.entry_points", lambda group: [fake_ep])

    fresh_registry._discover_plugins()

    assert "plugin_loader" in fresh_registry


def test_tool_registry_singleton_is_unchanged():
    """The module-level singleton must still be a ToolRegistry."""
    assert isinstance(filoma.tool_registry.tool_registry, filoma.tool_registry.ToolRegistry)


def test_entry_points_are_not_called_at_import_time(monkeypatch):
    """Entry points must be lazy — not invoked on ``import filoma``.

    Executes a *fresh copy* of the module under a private name instead of deleting
    ``filoma.tool_registry`` from ``sys.modules``: that left a second, empty registry
    singleton behind and broke whichever test ran next.
    """
    import importlib.util

    calls = []
    monkeypatch.setattr("importlib.metadata.entry_points", lambda group: calls.append(group) or [])

    spec = importlib.util.spec_from_file_location("filoma_tool_registry_fresh", filoma.tool_registry.__file__)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # @dataclass looks the defining module up by name
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)

    assert calls == []
    assert not module.tool_registry._plugins_loaded


def test_plugin_tool_names_only_include_entry_point_tools(fresh_registry, monkeypatch):
    """Tools registered directly are built-ins; only entry-point registrations count as plugin tools."""

    def builtin_tool(ctx, path: str) -> str:
        """Built-in."""
        return path

    fresh_registry.register(builtin_tool)

    def plugin_loader():
        def plugin_tool(ctx, path: str) -> str:
            """Plugin."""
            return path

        fresh_registry.register(plugin_tool)

    fake_ep = MagicMock()
    fake_ep.load.return_value = plugin_loader
    monkeypatch.setattr("importlib.metadata.entry_points", lambda group: [fake_ep])

    assert fresh_registry.plugin_tool_names() == frozenset({"plugin_tool"})
    assert "builtin_tool" in fresh_registry


def test_mcp_server_lists_plugin_tools(monkeypatch):
    """Plugin tools must reach MCP clients, not just the in-process agent."""
    pytest.importorskip("mcp")
    import asyncio

    import filoma.filaraki.tools  # noqa: F401 - registers the built-in tools
    from filoma import mcp_server
    from filoma.tool_registry import tool_registry

    def plugin_loader():
        def plugin_demo_tool(ctx, path: str) -> str:
            """Demo plugin tool."""
            return f"hello {path}"

        tool_registry.register(plugin_demo_tool)

    fake_ep = MagicMock()
    fake_ep.load.return_value = plugin_loader
    monkeypatch.setattr("importlib.metadata.entry_points", lambda group: [fake_ep])
    monkeypatch.setattr(tool_registry, "_plugins_loaded", False)

    try:
        listed = {t.name for t in asyncio.run(mcp_server.list_tools())}
        assert "plugin_demo_tool" in listed
        assert mcp_server._MCP_TOOL_NAMES <= listed
        # The instructions a client reads must mention it too, with the built-in count unchanged.
        instructions = mcp_server._server_instructions()
        assert "plugin_demo_tool: Demo plugin tool." in instructions
        assert f"{len(mcp_server._MCP_TOOL_NAMES)} filesystem analysis capabilities" in instructions
    finally:
        tool_registry._tools.pop("plugin_demo_tool", None)
        tool_registry._plugin_tool_names.discard("plugin_demo_tool")


def test_broken_plugin_is_skipped_without_affecting_others(fresh_registry, monkeypatch):
    def good_loader():
        def good_tool(ctx, path: str) -> str:
            """Works."""
            return path

        fresh_registry.register(good_tool)

    def broken_loader():
        raise ImportError("a dependency of this plugin is missing")

    broken_ep = MagicMock()
    broken_ep.name = "broken"
    broken_ep.load.return_value = broken_loader
    good_ep = MagicMock()
    good_ep.name = "good"
    good_ep.load.return_value = good_loader
    monkeypatch.setattr("importlib.metadata.entry_points", lambda group: [broken_ep, good_ep])

    specs = fresh_registry.list_specs()  # must not raise

    assert [s.name for s in specs] == ["good_tool"]
    assert fresh_registry.plugin_tool_names() == frozenset({"good_tool"})


def test_plugin_that_fails_midway_leaves_no_tools_behind(fresh_registry, monkeypatch):
    """A plugin that registered a tool and then raised must not leave that tool exposed."""

    def builtin_tool(ctx, path: str) -> str:
        """Built-in."""
        return path

    fresh_registry.register(builtin_tool)

    def half_loader():
        def first(ctx, path: str) -> str:
            """First."""
            return path

        def builtin_tool(ctx, path: str) -> str:  # noqa: F811 - overrides the built-in, then the plugin fails
            """Shadow."""
            return "shadow"

        fresh_registry.register(first)
        fresh_registry.register(builtin_tool)
        raise RuntimeError("fails after registering")

    ep = MagicMock()
    ep.name = "half"
    ep.load.return_value = half_loader
    monkeypatch.setattr("importlib.metadata.entry_points", lambda group: [ep])

    specs = {s.name: s for s in fresh_registry.list_specs()}

    assert set(specs) == {"builtin_tool"}
    assert specs["builtin_tool"].callable(None, "x") == "x", "the built-in must be restored, not shadowed"
    assert fresh_registry.plugin_tool_names() == frozenset()
