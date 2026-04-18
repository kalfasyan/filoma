"""Filaraki module for filoma.

Integrates PydanticAI to provide an intelligent interface for filesystem analysis.
"""

from typing import Any, Optional


def get_agent(model: Optional[Any] = None) -> Any:
    """Get a FilarakiAgent instance.

    Args:
    ----
        model: The model to use for the agent. If None, auto-detects provider in priority order:
               (1) Ollama on localhost:11434 (local, no keys needed, default model qwen2.5:14b),
               (2) Mistral AI if MISTRAL_API_KEY is set,
               (3) Google Gemini if GEMINI_API_KEY is set,
               (4) any OpenAI-compatible endpoint if FILOMA_FILARAKI_BASE_URL + OPENAI_API_KEY are set.

    """
    from .agent import FilarakiAgent

    return FilarakiAgent(model=model)
