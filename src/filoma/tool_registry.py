"""Single ToolRegistry consumed by both the Filaraki agent and MCP server.

Provides a `@tool_registry.register` decorator that records each tool's
metadata (name, description, parameter schema) alongside its callable.
Both adapters — the pydantic-ai Agent and the MCP stdio server — consume
the same registry, eliminating the duplication between
``filaraki/tools.py`` and ``mcp_server.py``.
"""

from __future__ import annotations

import importlib.metadata
import inspect
import re
from dataclasses import dataclass
from typing import Any, Callable, Optional, Union, get_args, get_origin


@dataclass
class ToolSpec:
    """Specification for a single registered tool."""

    name: str
    description: str
    callable: Callable[..., Any]
    param_schema: dict[str, Any]

    # Mapped from Python type annotations; "properties" maps param name
    # → {"type": "<json-type>", "description": "..."} and "required" is a
    # list of names without defaults (excluding ``ctx``).


# ---------------------------------------------------------------------------
# Public singleton — import this module-level instance everywhere.
# ---------------------------------------------------------------------------


class ToolRegistry:
    """Registry of all filoma tools.

    Both the Filaraki pydantic-ai Agent and the MCP stdio server adapt
    their surfaces from this single source of truth.
    """

    def __init__(self) -> None:  # noqa: D107
        self._tools: dict[str, ToolSpec] = {}
        self._plugins_loaded: bool = False

    # ------------------------------------------------------------------
    # Plugin discovery
    # ------------------------------------------------------------------

    def _discover_plugins(self) -> None:
        """Load third-party tools registered via ``importlib.metadata`` entry points.

        Scans the ``filoma.tools`` entry-point group once per process.
        Each entry-point callable is expected to call
        ``tool_registry.register(...)`` to register one or more tools.
        Plugins must not perform filesystem I/O or heavy imports at load time.
        """
        if self._plugins_loaded:
            return
        self._plugins_loaded = True
        entry_points = importlib.metadata.entry_points(group="filoma.tools")
        for ep in entry_points:
            _ = ep.load()()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, func: Callable[..., Any]) -> Callable[..., Any]:
        """Register *func* as a tool and return it unchanged.

        The function is NOT wrapped — pydantic-ai receives the raw
        callable exactly as before.
        """
        name = func.__name__
        description = _extract_description(func)
        param_schema = _extract_param_schema(func)
        self._tools[name] = ToolSpec(
            name=name,
            description=description,
            callable=func,
            param_schema=param_schema,
        )
        return func

    # ------------------------------------------------------------------
    # Read API
    # ------------------------------------------------------------------

    def list_specs(self) -> list[ToolSpec]:
        """Return all registered tool specs in registration order."""
        self._discover_plugins()
        return list(self._tools.values())

    def get_spec(self, name: str) -> Optional[ToolSpec]:
        """Get a single tool spec by name."""
        self._discover_plugins()
        return self._tools.get(name)

    def get_callable(self, name: str) -> Optional[Callable[..., Any]]:
        """Get a tool callable by name."""
        spec = self._tools.get(name)
        return spec.callable if spec else None

    def __len__(self) -> int:  # noqa: D105
        return len(self._tools)

    def __iter__(self):  # noqa: D105
        return iter(self._tools.values())

    def __contains__(self, name: str) -> bool:  # noqa: D105
        return name in self._tools


# Module-level singleton — ``from filoma.tool_registry import tool_registry``
tool_registry = ToolRegistry()


# ====================================================================
# Internal helpers
# ====================================================================

# Map Python type objects → JSON Schema type string
_PY_TO_JSON_TYPE: dict[Any, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
}


def _make_nullable(schema: dict[str, Any]) -> dict[str, Any]:
    """Widen a JSON Schema fragment to also accept a literal ``null``.

    Used for ``Optional[X]`` (``Union[X, None]``) parameters. Without this,
    a parameter like ``Optional[str] = None`` was advertised as a bare
    ``{"type": "string"}`` — technically true for the non-null case, but it
    meant a conforming MCP client that explicitly sent ``null`` for an
    unset optional argument (rather than omitting the key entirely) got
    rejected with a schema validation error like ``"None is not of type
    'string'"``, even though ``None`` is exactly what the Python default
    means. Widening ``type`` to include ``"null"`` (or adding a ``{"type":
    "null"}`` branch to an existing ``oneOf``) makes both forms valid.
    """
    if "oneOf" in schema:
        if {"type": "null"} not in schema["oneOf"]:
            schema["oneOf"].append({"type": "null"})
        return schema
    if "type" in schema:
        current = schema["type"]
        types = list(current) if isinstance(current, list) else [current]
        if "null" not in types:
            types.append("null")
        schema["type"] = types
    return schema


def _json_schema_for_annotation(annotation: Any) -> dict[str, Any]:
    """Best-effort mapping from a Python type annotation to a JSON Schema fragment.

    Returns e.g. ``{"type": "string"}`` for simple types, ``{"type": "array",
    "items": {...}}`` for lists, or a ``{"oneOf": [...]}`` fragment for
    multi-branch unions such as ``Union[str, List[str]]`` — a common "one or
    many" parameter pattern in this codebase (e.g. ``filter_by_extension``).

    Multi-branch unions used to flatten to a bare ``"string"`` type. That was
    a real bug: MCP clients that dutifully passed a real JSON array for such
    a parameter (as the tool's own docstring examples suggest they should)
    would have it silently re-serialized to a string like ``'[".md"]'``
    because the schema only advertised ``string``. That string then defeated
    the tool's comma/whitespace-splitting fallback, corrupting the filter
    into a value that could never match a real file and silently returning
    zero results. Exposing the true ``oneOf`` shape lets a conforming client
    send either a bare string or a real array correctly.

    ``Optional[X]`` (``Union[X, None]``) additionally widens the resulting
    schema to accept a literal ``null`` (see ``_make_nullable``), since the
    Python default of ``None`` for these parameters is a legitimate value a
    client may send explicitly, not just omit.
    """
    if annotation is None or annotation is inspect.Parameter.empty:
        return {"type": "string"}

    # Strip Optional (Union[X, None]), remembering whether None was a branch.
    origin = get_origin(annotation)
    if origin is Union:
        all_args = get_args(annotation)
        has_none = any(a is type(None) for a in all_args)  # noqa: E721
        branches = [a for a in all_args if a is not type(None)]  # noqa: E721
        if len(branches) == 1:
            schema = _json_schema_for_annotation(branches[0])
        else:
            # Multiple non-None branches (e.g. Union[str, List[str]]): expose
            # each branch's real schema via oneOf instead of collapsing to a
            # single lossy type.
            schemas: list[dict[str, Any]] = []
            for branch in branches:
                branch_schema = _json_schema_for_annotation(branch)
                if branch_schema not in schemas:
                    schemas.append(branch_schema)
            schema = schemas[0] if len(schemas) == 1 else {"oneOf": schemas}
        return _make_nullable(schema) if has_none else schema

    if origin is list:
        item_args = get_args(annotation)
        item_schema = _json_schema_for_annotation(item_args[0]) if item_args else {"type": "string"}
        return {"type": "array", "items": item_schema}

    return {"type": _PY_TO_JSON_TYPE.get(annotation, "string")}


def _extract_description(func: Callable[..., Any]) -> str:
    """Extract the first paragraph of a function's docstring as its description."""
    doc = inspect.getdoc(func)
    if not doc:
        return ""
    # Take everything up to the first blank line or Args: section
    lines = doc.splitlines()
    description_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            break
        if stripped.startswith("Args:") or stripped.startswith("Returns:") or stripped.startswith("Yields:"):
            break
        description_lines.append(stripped)
    return " ".join(description_lines)


def _parse_docstring_param_descriptions(func: Callable[..., Any]) -> dict[str, str]:
    """Extract per-parameter descriptions from a numpy-style docstring.

    Returns ``{param_name: description_text}``.
    """
    doc = inspect.getdoc(func)
    if not doc:
        return {}

    # Find the Args section
    args_match = re.search(r"^\s*Args:\s*$", doc, re.MULTILINE)
    if not args_match:
        return {}

    section_start = args_match.end()
    rest = doc[section_start:]

    # Parse each param line following the pattern "    param_name: description"
    param_desc: dict[str, str] = {}
    lines = rest.splitlines()
    current_param: Optional[str] = None
    current_desc: list[str] = []

    for line in lines:
        # Match "    param_name: description..." (numpy-style)
        pm = re.match(r"^\s+(\w[\w\d_]*)\s*:\s*(.*)", line)
        if pm:
            # Flush previous param
            if current_param is not None:
                param_desc[current_param] = " ".join(current_desc)
            current_param = pm.group(1)
            current_desc = [pm.group(2).strip()]
        elif current_param is not None and line.strip():
            # Continuation line for the current parameter description
            current_desc.append(line.strip())
        elif current_param is not None and not line.strip():
            # Blank line — end of args section
            param_desc[current_param] = " ".join(current_desc)
            current_param = None
            break

    if current_param is not None:
        param_desc[current_param] = " ".join(current_desc)

    return param_desc


def _extract_param_schema(func: Callable[..., Any]) -> dict[str, Any]:
    """Build a JSON Schema-compatible parameter description from the function signature.

    Returns a dict with ``properties`` and ``required`` keys suitable for
    embedding in an MCP ``inputSchema``.
    """
    sig = inspect.signature(func)
    param_descriptions = _parse_docstring_param_descriptions(func)
    properties: dict[str, dict[str, Any]] = {}
    required: list[str] = []

    for param_name, param in sig.parameters.items():
        # Skip pydantic-ai injected context
        if param_name == "ctx":
            continue
        # Skip variadic (**kwargs)
        if param.kind == inspect.Parameter.VAR_KEYWORD:
            continue
        if param.kind in (inspect.Parameter.VAR_POSITIONAL,):
            continue

        prop: dict[str, Any] = _json_schema_for_annotation(param.annotation)
        desc = param_descriptions.get(param_name, None)
        if desc:
            prop["description"] = desc

        properties[param_name] = prop

        # Required if no default value is present
        if param.default is inspect.Parameter.empty:
            required.append(param_name)

    return {"type": "object", "properties": properties, "required": required}
