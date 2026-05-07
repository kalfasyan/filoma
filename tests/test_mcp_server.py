"""Fast tests for the Filoma MCP server.

These tests verify the MCP server functionality without requiring
an actual MCP client connection. Tests are designed to run quickly.
"""

import tempfile
from pathlib import Path

import pytest

# Skip all tests if MCP is not installed
pytest.importorskip("mcp")

from mcp.types import Tool

from filoma.mcp_server import (
    TOOL_SCHEMAS,
    SimpleRunContext,
    _dataframe_state,
    _get_context,
    _is_graceful_stdio_disconnect,
    _save_context,
    call_tool,
    list_tools,
)


class TestMCPServerImports:
    """Test MCP server imports and basic structure."""

    def test_imports(self):
        """Test that MCP server module imports correctly."""
        assert len(TOOL_SCHEMAS) == 22

    def test_all_tools_have_descriptions(self):
        """Verify all tools have descriptions and schemas."""
        for name, spec in TOOL_SCHEMAS.items():
            assert "description" in spec
            assert "inputSchema" in spec
            assert spec["description"], f"Tool {name} has empty description"

    def test_tool_schema_structure(self):
        """Verify inputSchema follows JSON Schema structure."""
        for name, spec in TOOL_SCHEMAS.items():
            schema = spec["inputSchema"]
            assert schema["type"] == "object"
            assert "properties" in schema
            if "required" in schema:
                assert isinstance(schema["required"], list)


class TestToolRegistration:
    """Test tool registration and listing."""

    @pytest.mark.asyncio
    async def test_list_tools_returns_all_tools(self):
        """Test that list_tools returns all MCP tools."""
        tools = await list_tools()
        assert len(tools) == 22
        assert all(isinstance(t, Tool) for t in tools)

    @pytest.mark.asyncio
    async def test_tool_names_match_schemas(self):
        """Verify tool names match schema definitions."""
        tools = await list_tools()
        tool_names = {t.name for t in tools}
        schema_names = set(TOOL_SCHEMAS.keys())
        assert tool_names == schema_names

    @pytest.mark.asyncio
    async def test_expected_tools_present(self):
        """Verify key tools are present."""
        tools = await list_tools()
        tool_names = {t.name for t in tools}

        expected = {
            "count_files",
            "probe_directory",
            "get_directory_tree",
            "get_file_info",
            "search_files",
            "read_file",
            "create_dataset_dataframe",
            "summarize_dataframe",
            "analyze_image",
            "audit_dataset",
            "list_available_tools",
        }
        assert expected.issubset(tool_names)


class TestToolExecution:
    """Test tool execution with temp files."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory with test files."""
        with tempfile.TemporaryDirectory() as td:
            temp_path = Path(td)
            # Create test files
            (temp_path / "test1.txt").write_text("Hello World")
            (temp_path / "test2.txt").write_text("Test content")
            (temp_path / "script.py").write_text("print('hello')")
            # Create subdirectory
            subdir = temp_path / "subdir"
            subdir.mkdir()
            (subdir / "nested.txt").write_text("Nested file")
            yield temp_path

    @pytest.fixture(autouse=True)
    def clear_state(self):
        """Clear DataFrame state before each test."""
        _dataframe_state.clear()
        yield
        _dataframe_state.clear()

    @pytest.mark.asyncio
    async def test_list_available_tools(self):
        """Test list_available_tools returns tool documentation."""
        result = await call_tool("list_available_tools", {})
        assert len(result) == 1
        text = result[0].text
        assert "Filoma MCP Server" in text or "21" in text or "Tools" in text

    @pytest.mark.asyncio
    async def test_count_files(self, temp_dir):
        """Test count_files tool."""
        result = await call_tool("count_files", {"path": str(temp_dir)})
        assert len(result) == 1
        text = result[0].text
        assert "files" in text.lower() or "folders" in text.lower()

    @pytest.mark.asyncio
    async def test_probe_directory(self, temp_dir):
        """Test probe_directory with safety limits."""
        result = await call_tool("probe_directory", {"path": str(temp_dir), "max_depth": 1})
        assert len(result) == 1
        text = result[0].text
        assert "files" in text.lower() or "extensions" in text.lower()

    @pytest.mark.asyncio
    async def test_get_directory_tree(self, temp_dir):
        """Test get_directory_tree lists directory contents."""
        result = await call_tool("get_directory_tree", {"path": str(temp_dir)})
        assert len(result) == 1
        text = result[0].text
        # Should contain files or directory entries
        assert len(text) > 0

    @pytest.mark.asyncio
    async def test_get_file_info(self, temp_dir):
        """Test get_file_info returns file metadata."""
        test_file = temp_dir / "test1.txt"
        result = await call_tool("get_file_info", {"path": str(test_file)})
        assert len(result) == 1
        text = result[0].text
        assert "size" in text.lower() or "bytes" in text.lower()

    @pytest.mark.asyncio
    async def test_read_file(self, temp_dir):
        """Test read_file returns content with line numbers."""
        test_file = temp_dir / "test1.txt"
        result = await call_tool("read_file", {"path": str(test_file)})
        assert len(result) == 1
        text = result[0].text
        assert "Hello World" in text
        assert "```" in text  # Markdown code block

    @pytest.mark.asyncio
    async def test_read_file_with_line_range(self, temp_dir):
        """Test read_file with start_line and end_line."""
        test_file = temp_dir / "test1.txt"
        result = await call_tool(
            "read_file",
            {"path": str(test_file), "start_line": 1, "end_line": 1},
        )
        assert len(result) == 1
        text = result[0].text
        assert "Hello" in text


class TestDataFrameState:
    """Test DataFrame state management across tool calls."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory with test files."""
        with tempfile.TemporaryDirectory() as td:
            temp_path = Path(td)
            (temp_path / "file1.txt").write_text("content1")
            (temp_path / "file2.txt").write_text("content2")
            (temp_path / "script.py").write_text("code")
            yield temp_path

    @pytest.fixture(autouse=True)
    def clear_state(self):
        """Clear DataFrame state before each test."""
        _dataframe_state.clear()
        yield
        _dataframe_state.clear()

    @pytest.mark.asyncio
    async def test_create_dataset_dataframe_creates_state(self, temp_dir):
        """Test that create_dataset_dataframe stores state."""
        result = await call_tool("create_dataset_dataframe", {"path": str(temp_dir), "enrich": False})
        assert len(result) == 1
        # State should be saved
        assert "current_df" in _dataframe_state

    @pytest.mark.asyncio
    async def test_dataframe_head_requires_state(self, temp_dir):
        """Test dataframe_head works after creating DataFrame."""
        # First create the DataFrame
        await call_tool("create_dataset_dataframe", {"path": str(temp_dir), "enrich": False})

        # Then query it
        result = await call_tool("dataframe_head", {"n": 5})
        assert len(result) == 1
        text = result[0].text
        # Should show file entries
        assert len(text) > 0

    @pytest.mark.asyncio
    async def test_summarize_dataframe(self, temp_dir):
        """Test summarize_dataframe returns statistics."""
        # Create DataFrame first
        await call_tool("create_dataset_dataframe", {"path": str(temp_dir), "enrich": False})

        result = await call_tool("summarize_dataframe", {})
        assert len(result) == 1
        text = result[0].text
        # Should contain summary info
        assert len(text) > 0

    @pytest.mark.asyncio
    async def test_search_files_creates_state(self, temp_dir):
        """Test search_files creates DataFrame state."""
        result = await call_tool("search_files", {"path": str(temp_dir), "extension": "txt"})
        assert len(result) == 1
        # Should have created state
        assert "current_df" in _dataframe_state

    @pytest.mark.asyncio
    async def test_filter_by_extension(self, temp_dir):
        """Test filter_by_extension applies to state."""
        # Create state first
        await call_tool("create_dataset_dataframe", {"path": str(temp_dir), "enrich": False})

        # Filter by extension
        result = await call_tool("filter_by_extension", {"extensions": "txt"})
        assert len(result) == 1
        text = result[0].text
        assert "filtered" in text.lower() or "txt" in text.lower()


class TestMCPDisconnectHandling:
    """Test graceful handling of expected stdio disconnects."""

    def test_detects_simple_broken_pipe(self):
        """BrokenPipeError should be treated as graceful disconnect."""
        assert _is_graceful_stdio_disconnect(BrokenPipeError("broken pipe"))

    def test_detects_nested_exception_group(self):
        """Nested ExceptionGroup with disconnect errors should be graceful."""
        err = ExceptionGroup(
            "task group",
            [ExceptionGroup("nested", [BrokenPipeError("broken pipe")])],
        )
        assert _is_graceful_stdio_disconnect(err)

    def test_rejects_non_disconnect_error(self):
        """Unexpected runtime errors must not be swallowed."""
        assert not _is_graceful_stdio_disconnect(RuntimeError("boom"))


class TestErrorHandling:
    """Test error handling for invalid inputs."""

    @pytest.fixture(autouse=True)
    def clear_state(self):
        """Clear DataFrame state before each test."""
        _dataframe_state.clear()
        yield
        _dataframe_state.clear()

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error(self):
        """Test that unknown tools return an error message."""
        result = await call_tool("unknown_tool_xyz", {})
        assert len(result) == 1
        text = result[0].text
        assert "unknown" in text.lower() or "error" in text.lower()

    @pytest.mark.asyncio
    async def test_invalid_path_handled(self):
        """Test that invalid paths are handled gracefully."""
        result = await call_tool("count_files", {"path": "/nonexistent/path/xyz"})
        assert len(result) == 1
        # Should return an error message, not crash
        text = result[0].text
        assert "error" in text.lower() or "not found" in text.lower() or "no such" in text.lower()

    @pytest.mark.asyncio
    async def test_probe_directory_invalid_path(self):
        """Test probe_directory with invalid path."""
        result = await call_tool("probe_directory", {"path": "/this/path/does/not/exist"})
        assert len(result) == 1
        text = result[0].text
        assert "error" in text.lower() or "not" in text.lower()


class TestContextHelpers:
    """Test internal context helper functions."""

    @pytest.fixture(autouse=True)
    def clear_state(self):
        """Clear DataFrame state before each test."""
        _dataframe_state.clear()
        yield
        _dataframe_state.clear()

    def test_get_context_without_state(self):
        """Test _get_context with no existing state."""
        from filoma.filaraki.agent import FilarakiDeps

        deps = FilarakiDeps(working_dir="/tmp")
        ctx = _get_context(deps)
        assert ctx is not None
        assert ctx.deps.working_dir == "/tmp"
        assert ctx.deps.current_df is None

    def test_save_context_saves_dataframe(self):
        """Test _save_context stores DataFrame in state."""
        import polars as pl

        from filoma.filaraki.agent import FilarakiDeps

        # Create a mock context with a DataFrame
        deps = FilarakiDeps(working_dir="/tmp")
        deps.current_df = pl.DataFrame({"path": ["/tmp/test"], "size": [100]})
        ctx = SimpleRunContext(deps=deps)

        # Save it
        _save_context(ctx)

        # Verify state was saved
        assert "current_df" in _dataframe_state
        assert _dataframe_state["current_df"] is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
