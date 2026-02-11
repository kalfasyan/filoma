"""Brain module for filoma.

Integrates PydanticAI to provide an intelligent interface for filesystem analysis.
"""

from typing import Any, Optional


def get_agent(model: Optional[Any] = None) -> Any:
    """Get a FilomaAgent instance.

    Args:
        model: The model to use for the agent. If None, defaults to 'openai:gpt-4o'.

    """
    from .agent import FilomaAgent

    return FilomaAgent(model=model)
