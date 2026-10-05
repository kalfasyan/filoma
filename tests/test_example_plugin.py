"""The example plugin under ``examples/plugin_example`` must keep working with the real registry."""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

pytest.importorskip("pydantic_ai", reason="the example plugin needs the optional 'agent' extra")

from filoma.tool_registry import ToolRegistry  # noqa: E402

PLUGIN = Path(__file__).resolve().parent.parent / "examples" / "plugin_example" / "filoma_wordcount.py"

pytestmark = pytest.mark.skipif(not PLUGIN.exists(), reason="examples/ not available")


@pytest.fixture
def plugin_module():
    spec = importlib.util.spec_from_file_location("filoma_wordcount", PLUGIN)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop(spec.name, None)


def test_register_adds_a_well_formed_tool(plugin_module):
    registry = ToolRegistry()
    plugin_module.register(registry)

    spec = registry.get_spec("count_words")
    assert spec is not None
    assert spec.description == "Count the words in a text file."
    assert set(spec.param_schema["properties"]) == {"path", "max_bytes"}  # ctx is injected, never exposed
    assert spec.param_schema["required"] == ["path"]
    assert spec.param_schema["properties"]["path"]["type"] == "string"
    assert spec.param_schema["properties"]["max_bytes"]["type"] == "integer"
    assert "Path to a text file." in spec.param_schema["properties"]["path"]["description"]


def test_tool_counts_words_and_reports_errors(plugin_module, tmp_path):
    registry = ToolRegistry()
    plugin_module.register(registry)
    count_words = registry.get_callable("count_words")

    (tmp_path / "note.txt").write_text("one two  three\nfour")
    assert count_words(None, str(tmp_path / "note.txt")) == "note.txt: 4 words"
    assert count_words(None, str(tmp_path / "note.txt"), max_bytes=3) == "note.txt: 1 words"
    assert count_words(None, str(tmp_path / "missing.txt")).startswith("Error:")


def test_discovered_through_the_entry_point_group(plugin_module, monkeypatch):
    """Same path filoma takes for an installed plugin: entry point -> register() -> registry."""
    registry = ToolRegistry()
    entry_point = MagicMock()
    entry_point.name = "wordcount"
    entry_point.load.return_value = lambda: plugin_module.register(registry)
    monkeypatch.setattr("importlib.metadata.entry_points", lambda group: [entry_point] if group == "filoma.tools" else [])

    assert "count_words" in {spec.name for spec in registry.list_specs()}
    assert registry.plugin_tool_names() == frozenset({"count_words"})
