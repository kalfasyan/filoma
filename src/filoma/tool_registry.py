"""Single ToolRegistry consumed by both the Filaraki agent and MCP server.

Provides a `@tool_registry.register` decorator that records each tool's
metadata (name, description, parameter schema) alongside its callable.
Both adapters — the pydantic-ai Agent and the MCP stdio server — consume
the same registry, eliminating the duplication between
``filaraki/tools.py`` and ``mcp_server.py``.
"""

from __future__ import annotations

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
        return list(self._tools.values())

    def get_spec(self, name: str) -> Optional[ToolSpec]:
        """Get a single tool spec by name."""
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


def _json_type_from_annotation(annotation: Any) -> str:
    """Best-effort mapping from a Python type annotation to a JSON Schema type."""
    if annotation is None or annotation is inspect.Parameter.empty:
        return "string"

    # Strip Optional (Union[X, None])
    origin = get_origin(annotation)
    if origin is Union:
        args = [a for a in get_args(annotation) if a is not type(None)]  # noqa: E721
        if len(args) == 1:
            return _json_type_from_annotation(args[0])
        return "string"  # e.g. Union[str, List[str]] — flatten

    if origin is list:
        return "array"

    return _PY_TO_JSON_TYPE.get(annotation, "string")


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

        json_type = _json_type_from_annotation(param.annotation)

        prop: dict[str, Any] = {"type": json_type}
        desc = param_descriptions.get(param_name, None)
        if desc:
            prop["description"] = desc

        if json_type == "array":
            prop["items"] = {"type": "string"}

        properties[param_name] = prop

        # Required if no default value is present
        if param.default is inspect.Parameter.empty:
            required.append(param_name)

    return {"type": "object", "properties": properties, "required": required}
