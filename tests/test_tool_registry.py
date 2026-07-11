"""Tests for the ToolRegistry."""

import filoma.filaraki.tools  # noqa: F401 — triggers @tool_registry.register decorators
from filoma.tool_registry import ToolRegistry, ToolSpec, tool_registry


class TestToolRegistrySize:
    """Test that all expected tools are registered."""

    def test_registry_has_28_tools(self):
        assert len(tool_registry) == 28

    def test_core_tools_registered(self):
        names = {spec.name for spec in tool_registry.list_specs()}
        assert "count_files" in names
        assert "probe_directory" in names
        assert "find_duplicates" in names
        assert "get_file_info" in names
        assert "search_files" in names
        assert "audit_dataset" in names
        assert "list_available_tools" in names

    def test_unexposed_tool_not_registered(self):
        """analyze_dataframe is defined but not exposed to any surface."""
        names = {spec.name for spec in tool_registry.list_specs()}
        assert "analyze_dataframe" not in names


class TestToolSpecSchema:
    """Test that ToolSpec schemas are well-formed."""

    def test_count_files_schema(self):
        spec = tool_registry.get_spec("count_files")
        assert spec is not None
        assert spec.description
        assert spec.callable is not None

        schema = spec.param_schema
        assert schema["type"] == "object"
        assert "path" in schema["properties"]
        assert schema["properties"]["path"]["type"] == "string"
        assert "path" in schema["required"]

    def test_audit_dataset_schema(self):
        spec = tool_registry.get_spec("audit_dataset")
        assert spec is not None

        schema = spec.param_schema
        assert schema["type"] == "object"
        assert "path" in schema["properties"]
        assert "mode" in schema["properties"]
        assert "show_evidence" in schema["properties"]
        assert "export_path" in schema["properties"]
        assert "export_format" in schema["properties"]
        # Only path is required
        assert schema["required"] == ["path"]

    def test_list_available_tools_schema(self):
        spec = tool_registry.get_spec("list_available_tools")
        assert spec is not None
        assert spec.param_schema["required"] == []
        assert spec.param_schema["properties"] == {}

    def test_search_files_schema(self):
        spec = tool_registry.get_spec("search_files")
        assert spec is not None

        schema = spec.param_schema
        props = schema["properties"]
        assert "path" in props
        assert "pattern" in props
        assert "extension" in props
        assert "min_size" in props
        assert "max_depth" in props
        assert "include_hidden" in props
        assert "ignore_git_files" in props
        # Only path is required
        assert schema["required"] == ["path"]

    def test_filter_by_extension_type(self):
        """filter_by_extension has Union[str, List[str]] → should flatten to string."""
        spec = tool_registry.get_spec("filter_by_extension")
        assert spec is not None
        assert spec.param_schema["properties"]["extensions"]["type"] == "string"


class TestDescriptionExtraction:
    """Test that docstring descriptions are extracted correctly."""

    def test_count_files_has_description(self):
        spec = tool_registry.get_spec("count_files")
        assert "Count the total number" in spec.description

    def test_all_registered_tools_have_descriptions(self):
        for spec in tool_registry.list_specs():
            assert spec.description, f"Tool '{spec.name}' has no description"

    def test_all_registered_tools_have_schemas(self):
        for spec in tool_registry.list_specs():
            assert spec.param_schema["type"] == "object"
            assert "properties" in spec.param_schema
            assert "required" in spec.param_schema
            required = set(spec.param_schema["required"])
            props = set(spec.param_schema["properties"])
            # Required params must appear in properties
            assert required <= props, f"Tool '{spec.name}': required {required} not subset of properties {props}"


class TestRegistryAPI:
    """Test the ToolRegistry read API."""

    def test_contains(self):
        assert "count_files" in tool_registry
        assert "nonexistent_tool" not in tool_registry

    def test_get_spec(self):
        spec = tool_registry.get_spec("count_files")
        assert isinstance(spec, ToolSpec)
        assert spec.name == "count_files"

    def test_get_spec_nonexistent(self):
        assert tool_registry.get_spec("nonexistent") is None

    def test_get_callable(self):
        func = tool_registry.get_callable("count_files")
        assert callable(func)

    def test_get_callable_nonexistent(self):
        assert tool_registry.get_callable("nonexistent") is None

    def test_list_specs_returns_correct_count(self):
        specs = tool_registry.list_specs()
        assert len(specs) == 28
        assert all(isinstance(s, ToolSpec) for s in specs)


class TestFreshRegistry:
    """Test that a fresh ToolRegistry starts empty."""

    def test_empty_registry(self):
        reg = ToolRegistry()
        assert len(reg) == 0
        assert reg.list_specs() == []

    def test_register_decorator(self):
        reg = ToolRegistry()

        @reg.register
        def dummy_tool(ctx, path: str, verbose: bool = False) -> str:
            """A dummy tool for testing.

            Args:
            ----
                ctx: The run context.
                path: The path to operate on.
                verbose: Whether to be verbose.
            """
            return "ok"

        assert len(reg) == 1
        spec = reg.get_spec("dummy_tool")
        assert spec.name == "dummy_tool"
        assert "A dummy tool" in spec.description
        assert spec.callable is not None
        assert spec.param_schema["required"] == ["path"]
        assert "path" in spec.param_schema["properties"]
        assert "verbose" in spec.param_schema["properties"]
        # Type mapping
        assert spec.param_schema["properties"]["path"]["type"] == "string"
        assert spec.param_schema["properties"]["verbose"]["type"] == "boolean"
