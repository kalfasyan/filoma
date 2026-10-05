# Writing a filoma plugin

Third-party packages can add tools to the Filaraki agent and to the MCP server without touching filoma itself. A plugin is an ordinary Python package that declares an entry point in the `filoma.tools` group; filoma finds it with `importlib.metadata` and calls it once, lazily, the first time the tool list is needed.

A complete, installable example lives in [`examples/plugin_example/`](https://github.com/kalfasyan/filoma/tree/main/examples/plugin_example) (a `count_words` tool). Try it:

```bash
pip install "filoma[agent]"
pip install -e examples/plugin_example
filoma mcp serve          # count_words is now listed alongside the built-in tools
```

## Declare the entry point

```toml
# pyproject.toml of your plugin
[project]
name = "filoma-wordcount"
dependencies = ["filoma[agent]"]

[project.entry-points."filoma.tools"]
wordcount = "filoma_wordcount:register"
```

The value is `<module>:<callable>`. filoma calls the callable with no arguments.

## Register tools

```python
from typing import Any


def register() -> None:
    from pydantic_ai import RunContext  # provided by the "agent" extra
    from filoma.tool_registry import tool_registry

    @tool_registry.register
    def count_words(ctx: RunContext[Any], path: str, max_bytes: int = 1_000_000) -> str:
        """Count the words in a text file.

        Args:
            ctx: The run context (injected by filoma; not shown to the model).
            path: Path to a text file.
            max_bytes: Read at most this many bytes.

        """
        ...
```

What filoma derives from your function:

- **Name**: the function name. Names must be unique; registering an existing name replaces the earlier tool, so do not reuse a built-in's name.
- **Description**: the first paragraph of the docstring.
- **Parameters**: from the type hints (`str`, `int`, `float`, `bool`, `list[...]`, `Optional[...]` and `Union[...]` are mapped to JSON Schema). A parameter is required when it has no default. Parameter descriptions come from the `Args:` section of the docstring.
- **`ctx`**: the first parameter must be named `ctx` and annotated `RunContext[Any]`. It is injected by filoma and never exposed to the model.
- **Return value**: a string. That is what the model or MCP client reads.

## Rules for plugins

- **Keep `register()` cheap.** It runs on first use of the tool list, in the agent and MCP server startup path. No filesystem I/O and no heavy imports at load time; import inside the tool body.
- **Tools should be read-only unless clearly named otherwise.** Agents call tools autonomously.
- **A broken plugin is skipped.** If your entry point raises, filoma logs a warning and carries on with the other plugins and the built-in tools.

## Where your tools show up

| Surface                            | Plugin tools                                                                           |
| ---------------------------------- | -------------------------------------------------------------------------------------- |
| `flm.ask()`, `filoma chat`         | Available to the agent, like every registered tool                                     |
| `filoma mcp serve`                 | Listed and callable, next to the built-in tools that the server exposes                |
| `filoma audit`, `filoma.probe(..)` | Not involved: plugins only extend the agent/MCP surface, not the scanners or the audit |

## Testing a plugin

Register into a fresh `ToolRegistry` rather than the global one, then call the tool directly:

```python
from filoma.tool_registry import ToolRegistry
import filoma_wordcount

registry = ToolRegistry()
filoma_wordcount.register(registry)  # let register() accept an optional registry for tests
count_words = registry.get_callable("count_words")
assert count_words(None, "notes.txt") == "notes.txt: 4 words"
```

See `tests/test_example_plugin.py` in the filoma repository for a version that also checks the generated schema and discovery through the entry-point group.
