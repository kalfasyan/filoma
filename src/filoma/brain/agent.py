"""Agent implementation for filoma."""

import os
from dataclasses import dataclass
from typing import Any, List, Optional, Union

from loguru import logger
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models import Model

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    logger.debug("python-dotenv not installed, skipping .env loading")

from . import tools


@dataclass
class FilomaDeps:
    """Dependencies for the FilomaAgent."""

    working_dir: str = "."


class FilomaAgent:
    """An intelligent agent for interacting with filoma."""

    def __init__(
        self,
        model: Optional[Union[str, Model]] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        """Initialize the FilomaAgent.

        Args:
            model: The model string (e.g. 'openai:gpt-4o', 'mistral:mistral-small-latest')
                   or a Model instance.
            base_url: Optional base URL for OpenAI-compatible APIs.
            api_key: Optional API key.

        """
        self.model = self._resolve_model(model, base_url, api_key)

        self.agent = Agent(
            self.model,
            deps_type=FilomaDeps,
            system_prompt=(
                "You are an expert filesystem analyst using the 'filoma' library. "
                "Your goal is to help users understand their directory structures, "
                "find specific files, and analyze file metadata. "
                "\n\n"
                "CRITICAL INSTRUCTIONS FOR FILE COUNTING:\n"
                "- When the user asks 'how many files' or wants a file count, ALWAYS use the count_files tool.\n"
                "- The count_files tool performs a complete scan of the entire directory tree.\n"
                "- Never use probe_directory for simple file counting - use count_files instead.\n"
                "- Report the exact number from count_files. Do not estimate or modify it.\n"
                "\n\n"
                "CRITICAL INSTRUCTIONS FOR PATH HANDLING:\n"
                "- When the user says 'in .', use path='.'\n"
                "- When the user says 'current directory', use path='.'\n"
                "- When the user says 'home directory' or '~', use path='~'\n"
                "- ALWAYS use the path exactly as the user specified.\n"
                "- Do NOT guess or modify paths.\n"
                "\n\n"
                "CRITICAL INSTRUCTIONS FOR DATA REPORTING:\n"
                "1. When reporting file counts, use the EXACT number from the tool output.\n"
                "2. DO NOT calculate or estimate.\n"
                "3. Be precise and technical.\n"
                "4. Include the comma separator for large numbers (e.g., '77,917' not '77917')."
            ),
        )

        # Register tools using the .tool() method as allowed by Agent
        # Note: the tools themselves must accept RunContext[FilomaDeps]
        self.agent.tool(tools.count_files)
        self.agent.tool(tools.probe_directory)
        self.agent.tool(tools.find_duplicates)
        self.agent.tool(tools.get_file_info)

    def _resolve_model(
        self,
        model: Optional[Union[str, Model]],
        base_url: Optional[str],
        api_key: Optional[str],
    ) -> Union[str, Model]:
        """Resolve the model name or instance for pydantic-ai."""
        if model and not isinstance(model, str):
            return model

        # Logic: Priority to explicit Base URL (Scenario B/D: Ollama/Local)
        env_base_url = base_url or os.getenv("FILOMA_BRAIN_BASE_URL")
        env_model = model or os.getenv("FILOMA_BRAIN_MODEL")
        env_api_key = api_key or os.getenv("FILOMA_BRAIN_API_KEY")

        if env_base_url:
            logger.info(f"Connecting to custom OpenAI-compatible endpoint: {env_base_url}")
            from pydantic_ai.models.openai import OpenAIModel

            m_name = env_model or "ollama:llama3"
            # Using keyword arguments for the latest pydantic-ai/OpenAI provider
            return OpenAIModel(m_name, base_url=env_base_url, api_key=env_api_key)

        # Logic: Scenario A (Mistral)
        mistral_key = os.getenv("MISTRAL_API_KEY")
        if mistral_key:
            m_name = env_model or "mistral:mistral-small-latest"
            logger.info(f"Using Mistral AI with model '{m_name}' (MISTRAL_API_KEY found).")
            # If it doesn't have the prefix, add it for pydantic-ai resolution
            if ":" not in m_name:
                m_name = f"mistral:{m_name}"
            return m_name

        # Logic: Scenario C (OpenAI)
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            m_name = env_model or "openai:gpt-4o"
            logger.info(f"Using OpenAI with model '{m_name}' (OPENAI_API_KEY found).")
            if ":" not in m_name:
                m_name = f"openai:{m_name}"
            return m_name

        # Default Fallback
        logger.warning("No AI configuration found. Defaulting to 'mistral:mistral-small-latest'.")
        return "mistral:mistral-small-latest"

    async def run(
        self,
        prompt: str,
        deps: Optional[FilomaDeps] = None,
        message_history: Optional[List[ModelMessage]] = None,
    ) -> Any:
        """Run the agent with a prompt.

        Returns a result object from pydantic-ai.
        """
        if deps is None:
            deps = FilomaDeps()

        # Simple run - pydantic-ai returns an AgentRunResult
        result = await self.agent.run(prompt, deps=deps, message_history=message_history)

        # Latest pydantic-ai (v1.58+) stores the final response in .data
        # We ensure it's easily accessible for the caller.
        return result
