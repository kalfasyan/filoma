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
    """Entry points must be lazy — not invoked on ``import filoma``."""
    # Re-import the module to confirm no discovery at import time
    if "filoma.tool_registry" in sys.modules:
        del sys.modules["filoma.tool_registry"]
    import filoma.tool_registry as tr  # noqa: F811

    assert not tr.tool_registry._plugins_loaded
