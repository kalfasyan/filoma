import importlib
from pathlib import Path

import filoma.filaraki.tools  # noqa: F401 — triggers @tool_registry.register
from filoma.filaraki.agent import FilarakiDeps
from filoma.tool_registry import tool_registry


class FakeContext:
    """Minimal RunContext-like object for testing tools directly."""

    def __init__(self, deps=None):
        self.deps = deps or FilarakiDeps()


def test_index_for_rag_is_registered():
    spec = tool_registry.get_spec("index_for_rag")
    assert spec is not None


def test_search_rag_is_registered():
    spec = tool_registry.get_spec("search_rag")
    assert spec is not None


def test_search_rag_no_store():
    ctx = FakeContext()
    func = tool_registry.get_callable("search_rag")
    result = func(ctx, "test query")
    assert "No RAG store indexed" in result or "index_for_rag" in result


def test_index_for_rag_requires_lancedb(tmp_path):
    try:
        importlib.import_module("lancedb")
    except ImportError:
        has_lancedb = False
    else:
        has_lancedb = True

    tmp_path = Path(tmp_path)
    (tmp_path / "readme.md").write_text("# Test\n")

    ctx = FakeContext()
    func = tool_registry.get_callable("index_for_rag")
    result = func(ctx, str(tmp_path))

    if has_lancedb:
        assert "Indexed" in result or "Error" not in result
    else:
        assert "Error" in result or "not available" in result
