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

import filoma.filaraki.tools  # noqa: F401 — ensures tools are registered
from filoma.mcp_server import (
    _MCP_TOOL_NAMES,
    _NO_SESSION,
    SimpleRunContext,
    _dataframe_state,
    _get_context,
    _is_graceful_stdio_disconnect,
    _save_context,
    call_tool,
    list_tools,
)
from filoma.tool_registry import tool_registry


class TestMCPServerImports:
    """Test MCP server imports and basic structure."""

    def test_imports(self):
        """Test that MCP server module imports correctly."""
        assert len(_MCP_TOOL_NAMES) == 29

    def test_all_tools_have_descriptions(self):
        """Verify all tools have descriptions and schemas."""
        for spec in tool_registry.list_specs():
            if spec.name not in _MCP_TOOL_NAMES:
                continue
            assert spec.description, f"Tool {spec.name} has empty description"
            assert spec.param_schema["type"] == "object"
            assert "properties" in spec.param_schema

    def test_tool_schema_structure(self):
        """Verify inputSchema follows JSON Schema structure."""
        for spec in tool_registry.list_specs():
            if spec.name not in _MCP_TOOL_NAMES:
                continue
            schema = spec.param_schema
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
        assert len(tools) == 29
        assert all(isinstance(t, Tool) for t in tools)

    @pytest.mark.asyncio
    async def test_tool_names_match_schemas(self):
        """Verify tool names match schema definitions."""
        tools = await list_tools()
        tool_names = {t.name for t in tools}
        assert tool_names == _MCP_TOOL_NAMES

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

    @pytest.fixture
    def mirrored_dir(self):
        """Two directories that are near-perfect mirrors of each other."""
        with tempfile.TemporaryDirectory() as td:
            temp_path = Path(td)
            original = temp_path / "original"
            mirror = temp_path / "mirror"
            original.mkdir()
            mirror.mkdir()
            for i in range(5):
                content = f"identical content {i}"
                (original / f"file{i}.txt").write_text(content)
                (mirror / f"file{i}.txt").write_text(content)
            # One unique file so the dirs aren't a 100% byte-for-byte match.
            (original / "unique.txt").write_text("only in original")
            yield temp_path

    @pytest.mark.asyncio
    async def test_find_duplicates_flags_near_duplicate_directories(self, mirrored_dir):
        """The default report should proactively call out the mirrored directory pair."""
        result = await call_tool("find_duplicates", {"path": str(mirrored_dir), "ignore_safety_limits": True})
        assert len(result) == 1
        text = result[0].text
        assert "NEAR-DUPLICATE" in text
        assert "original" in text and "mirror" in text

    @pytest.mark.asyncio
    async def test_find_duplicates_group_by_directory_is_compact(self, mirrored_dir):
        """group_by_directory=True must return a directory-pair summary, not every file."""
        result = await call_tool("find_duplicates", {"path": str(mirrored_dir), "ignore_safety_limits": True, "group_by_directory": True})
        assert len(result) == 1
        text = result[0].text
        assert "DIRECTORY-PAIR OVERLAP" in text
        assert "5" in text  # 5 shared files
        # Must NOT enumerate individual file paths/groups the way the default report does.
        assert "Group 1:" not in text

    @pytest.mark.asyncio
    async def test_find_duplicates_caps_group_listing(self, tmp_path, monkeypatch):
        """The default (non-grouped) report must cap how many full groups it lists."""
        monkeypatch.setattr("filoma.filaraki.tools._DUPLICATE_GROUPS_DISPLAY_LIMIT", 2)

        big_dir = tmp_path / "many_dupes"
        big_dir.mkdir()
        for i in range(5):
            (big_dir / f"a{i}.txt").write_text(f"same content {i}")
            (big_dir / f"b{i}.txt").write_text(f"same content {i}")

        result = await call_tool("find_duplicates", {"path": str(big_dir), "ignore_safety_limits": True})
        text = result[0].text
        assert text.count("Group ") <= 2
        assert "more duplicate groups not shown" in text


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
        # State should be saved under the fallback "no live session" key
        # (these tests call call_tool() directly, with no real MCP session)
        assert "current_df" in _dataframe_state[_NO_SESSION]

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
        assert "current_df" in _dataframe_state[_NO_SESSION]

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

    @pytest.mark.asyncio
    async def test_filter_by_extension_accepts_json_stringified_array(self, temp_dir):
        """A client that JSON-encodes a real array as a string must still work.

        Regression test for the bug where a schema that only advertised
        "string" caused conforming clients to send '[".txt"]' (a string)
        instead of a real array, which used to silently match zero files.
        """
        await call_tool("create_dataset_dataframe", {"path": str(temp_dir), "enrich": False})

        result = await call_tool("filter_by_extension", {"extensions": '[".txt"]'})
        text = result[0].text
        assert "2 files" in text
        df = _dataframe_state[_NO_SESSION]["current_df"]
        assert len(df) == 2

    @pytest.mark.asyncio
    async def test_filter_by_extension_on_already_empty_dataframe_warns(self, temp_dir):
        """Filtering an already-empty DataFrame should say so, not report a
        fresh "successful" filter — that message previously masked the real
        bug (a prior filter call had already zeroed out current_df) and cost
        several confusing extra tool calls before the root cause was found.
        """
        await call_tool("create_dataset_dataframe", {"path": str(temp_dir), "enrich": False})

        # First filter to a nonexistent extension: legitimately 0 rows.
        first = await call_tool("filter_by_extension", {"extensions": "nonexistent"})
        assert "0 files" in first[0].text

        # Filtering again on the now-empty DataFrame must be called out
        # explicitly instead of looking like an independent new result.
        second = await call_tool("filter_by_extension", {"extensions": "txt"})
        assert "already has 0 rows" in second[0].text

    @pytest.mark.asyncio
    async def test_filter_by_pattern_on_already_empty_dataframe_warns(self, temp_dir):
        """filter_by_pattern must call out an already-empty DataFrame too."""
        await call_tool("create_dataset_dataframe", {"path": str(temp_dir), "enrich": False})
        await call_tool("filter_by_extension", {"extensions": "nonexistent"})

        result = await call_tool("filter_by_pattern", {"pattern": r"\.txt$"})
        assert "already has 0 rows" in result[0].text

    @pytest.mark.asyncio
    async def test_add_duplicate_cols(self, temp_dir):
        """Test add_duplicate_cols flags exact duplicates in the stored DataFrame."""
        (temp_dir / "dup1.txt").write_text("same bytes")
        (temp_dir / "dup2.txt").write_text("same bytes")

        await call_tool("create_dataset_dataframe", {"path": str(temp_dir), "enrich": False})

        result = await call_tool("add_duplicate_cols", {})
        assert len(result) == 1
        text = result[0].text
        assert "is_exact_duplicate" in text

        df = _dataframe_state[_NO_SESSION]["current_df"]
        assert "is_exact_duplicate" in df.to_polars().columns

    @pytest.mark.asyncio
    async def test_add_corruption_cols(self, temp_dir):
        """Test add_corruption_cols flags zero-byte files in the stored DataFrame."""
        (temp_dir / "empty.txt").write_text("")

        await call_tool("create_dataset_dataframe", {"path": str(temp_dir), "enrich": False})

        result = await call_tool("add_corruption_cols", {})
        assert len(result) == 1
        text = result[0].text
        assert "is_corrupt" in text

        df = _dataframe_state[_NO_SESSION]["current_df"]
        pdf = df.to_polars()
        assert "is_corrupt" in pdf.columns
        reasons = dict(zip(pdf["path"].to_list(), pdf["corruption_reason"].to_list()))
        expected_path = str((temp_dir / "empty.txt").resolve())
        assert reasons[expected_path] == "zero_byte"

    @pytest.mark.asyncio
    async def test_add_embedding_cols(self, temp_dir, monkeypatch):
        """Test add_embedding_cols attaches an embedding column to the stored DataFrame."""
        monkeypatch.setattr("filoma.core.rag._resolve_embedder", lambda: (lambda texts: [[1.0, 2.0, 3.0] for _ in texts]))

        await call_tool("create_dataset_dataframe", {"path": str(temp_dir), "enrich": False})

        result = await call_tool("add_embedding_cols", {})
        assert len(result) == 1
        text = result[0].text
        assert "embedding" in text

        df = _dataframe_state[_NO_SESSION]["current_df"]
        pdf = df.to_polars()
        assert "embedding" in pdf.columns
        # file1.txt/file2.txt/script.py are all recognized text files.
        assert pdf["embedding"].is_not_null().sum() == 3

    @pytest.mark.asyncio
    async def test_add_semantic_similarity_cols(self, temp_dir, monkeypatch):
        """Test add_semantic_similarity_cols requires embeddings and attaches neighbor columns."""
        monkeypatch.setattr("filoma.core.rag._resolve_embedder", lambda: (lambda texts: [[1.0, 2.0, 3.0] for _ in texts]))

        await call_tool("create_dataset_dataframe", {"path": str(temp_dir), "enrich": False})

        # Without embeddings first, the tool should surface the ValueError.
        missing = await call_tool("add_semantic_similarity_cols", {})
        assert "embedding" in missing[0].text.lower()

        await call_tool("add_embedding_cols", {})
        result = await call_tool("add_semantic_similarity_cols", {"top_k": 1})
        assert len(result) == 1
        text = result[0].text
        assert "nearest_neighbor" in text.lower()

        df = _dataframe_state[_NO_SESSION]["current_df"]
        pdf = df.to_polars()
        assert "nearest_neighbor_paths" in pdf.columns
        assert "nearest_neighbor_similarities" in pdf.columns

    @pytest.mark.asyncio
    async def test_add_metadata_embedding_cols(self, temp_dir):
        """Test add_metadata_embedding_cols attaches a metadata_embedding column."""
        await call_tool("create_dataset_dataframe", {"path": str(temp_dir), "enrich": True})

        result = await call_tool("add_metadata_embedding_cols", {})
        assert len(result) == 1
        text = result[0].text
        assert "metadata_embedding" in text

        df = _dataframe_state[_NO_SESSION]["current_df"]
        pdf = df.to_polars()
        assert "metadata_embedding" in pdf.columns
        assert pdf["metadata_embedding"].null_count() == 0

    @pytest.mark.asyncio
    async def test_add_metadata_embedding_cols_requires_usable_columns(self, temp_dir):
        """Without enrichment, there are no metadata columns to build from."""
        await call_tool("create_dataset_dataframe", {"path": str(temp_dir), "enrich": False})

        result = await call_tool("add_metadata_embedding_cols", {})
        assert "error" in result[0].text.lower()

    @pytest.mark.asyncio
    async def test_add_semantic_similarity_cols_blends_metadata(self, temp_dir, monkeypatch):
        """Passing metadata_embedding_col should change similarity scores vs. content-only."""
        monkeypatch.setattr("filoma.core.rag._resolve_embedder", lambda: (lambda texts: [[1.0, 2.0, 3.0] for _ in texts]))

        await call_tool("create_dataset_dataframe", {"path": str(temp_dir), "enrich": True})
        await call_tool("add_embedding_cols", {})
        await call_tool("add_metadata_embedding_cols", {})

        result = await call_tool("add_semantic_similarity_cols", {"metadata_embedding_col": "metadata_embedding", "content_weight": 0.5, "top_k": 1})
        assert len(result) == 1
        assert "nearest_neighbor" in result[0].text.lower()

        df = _dataframe_state[_NO_SESSION]["current_df"]
        pdf = df.to_polars()
        assert "nearest_neighbor_paths" in pdf.columns

    @pytest.mark.asyncio
    async def test_add_embedding_cols_refuses_over_safety_limit(self, tmp_path, monkeypatch):
        """add_embedding_cols must refuse (not hang) when too many files look embeddable."""
        monkeypatch.setattr("filoma.core.rag._resolve_embedder", lambda: (lambda texts: [[1.0, 2.0, 3.0] for _ in texts]))
        monkeypatch.setattr("filoma.filaraki.tools._EMBED_SAFETY_LIMIT", 3)

        big_dir = tmp_path / "big"
        big_dir.mkdir()
        for i in range(10):
            (big_dir / f"file{i}.txt").write_text(f"content {i}")

        await call_tool("create_dataset_dataframe", {"path": str(big_dir), "enrich": False})

        result = await call_tool("add_embedding_cols", {})
        assert len(result) == 1
        text = result[0].text
        assert "safety limit" in text.lower()

        # The DataFrame must be untouched — no embedding column, no long-running work done.
        df = _dataframe_state[_NO_SESSION]["current_df"]
        assert "embedding" not in df.to_polars().columns

    @pytest.mark.asyncio
    async def test_add_embedding_cols_ignore_safety_limits_proceeds(self, tmp_path, monkeypatch):
        """ignore_safety_limits=True must bypass the safety refusal."""
        monkeypatch.setattr("filoma.core.rag._resolve_embedder", lambda: (lambda texts: [[1.0, 2.0, 3.0] for _ in texts]))
        monkeypatch.setattr("filoma.filaraki.tools._EMBED_SAFETY_LIMIT", 3)

        big_dir = tmp_path / "big"
        big_dir.mkdir()
        for i in range(10):
            (big_dir / f"file{i}.txt").write_text(f"content {i}")

        await call_tool("create_dataset_dataframe", {"path": str(big_dir), "enrich": False})

        result = await call_tool("add_embedding_cols", {"ignore_safety_limits": True})
        text = result[0].text
        assert "embedding" in text.lower()
        assert "safety limit" not in text.lower()

        df = _dataframe_state[_NO_SESSION]["current_df"]
        assert "embedding" in df.to_polars().columns

    @pytest.mark.asyncio
    async def test_export_then_load_dataframe_roundtrip(self, temp_dir, tmp_path):
        """load_dataframe must be able to resume a DataFrame saved via export_dataframe."""
        await call_tool("create_dataset_dataframe", {"path": str(temp_dir), "enrich": True})
        original_rows = len(_dataframe_state[_NO_SESSION]["current_df"])
        original_columns = set(_dataframe_state[_NO_SESSION]["current_df"].columns)

        export_path = tmp_path / "saved.parquet"
        export_result = await call_tool("export_dataframe", {"path": str(export_path), "format": "parquet"})
        assert export_path.exists()
        assert "export" in export_result[0].text.lower() or "success" in export_result[0].text.lower()

        # Simulate a fresh session: no DataFrame loaded.
        _dataframe_state.pop(_NO_SESSION, None)
        missing = await call_tool("dataframe_head", {})
        assert "no dataframe" in missing[0].text.lower()

        load_result = await call_tool("load_dataframe", {"path": str(export_path)})
        assert len(load_result) == 1
        text = load_result[0].text
        assert "loaded" in text.lower()

        df = _dataframe_state[_NO_SESSION]["current_df"]
        assert len(df) == original_rows
        assert set(df.columns) == original_columns

    @pytest.mark.asyncio
    async def test_load_dataframe_missing_file(self, tmp_path):
        """load_dataframe must surface a clear error for a nonexistent file, not crash."""
        result = await call_tool("load_dataframe", {"path": str(tmp_path / "does_not_exist.parquet")})
        assert len(result) == 1
        assert "error" in result[0].text.lower()

    @pytest.mark.asyncio
    async def test_load_dataframe_infers_format_from_extension(self, tmp_path):
        """format is optional and should be inferred from the file suffix."""
        from filoma.dataframe import DataFrame

        df = DataFrame({"path": ["a.txt", "b.txt"]})
        csv_path = tmp_path / "saved.csv"
        df.save_csv(csv_path)

        result = await call_tool("load_dataframe", {"path": str(csv_path)})
        assert "loaded" in result[0].text.lower()

        loaded = _dataframe_state[_NO_SESSION]["current_df"]
        assert len(loaded) == 2


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

        # Verify state was saved under the fallback "no live session" key
        assert "current_df" in _dataframe_state[_NO_SESSION]
        assert _dataframe_state[_NO_SESSION]["current_df"] is not None

    def test_dataframe_state_is_isolated_per_session(self, monkeypatch):
        """Two distinct sessions must not see each other's cached DataFrame.

        Regression test for the per-connection WeakKeyDictionary state: this
        directly exercises the isolation property (not just the _NO_SESSION
        fallback path that the other tests in this class cover).
        """
        import polars as pl

        import filoma.mcp_server as mcp_module
        from filoma.filaraki.agent import FilarakiDeps

        class _FakeSession:
            pass

        session_a = _FakeSession()
        session_b = _FakeSession()

        # Session A stores a DataFrame.
        monkeypatch.setattr(mcp_module, "_session_key", lambda: session_a)
        deps_a = FilarakiDeps(working_dir="/tmp")
        deps_a.current_df = pl.DataFrame({"path": ["/tmp/a"]})
        mcp_module._save_context(SimpleRunContext(deps=deps_a))

        # Session B must start with no DataFrame, even though A just saved one.
        monkeypatch.setattr(mcp_module, "_session_key", lambda: session_b)
        ctx_b = mcp_module._get_context(FilarakiDeps(working_dir="/tmp"))
        assert ctx_b.deps.current_df is None

        # Session A must still see its own DataFrame, unaffected by B.
        monkeypatch.setattr(mcp_module, "_session_key", lambda: session_a)
        ctx_a = mcp_module._get_context(FilarakiDeps(working_dir="/tmp"))
        assert ctx_a.deps.current_df is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
