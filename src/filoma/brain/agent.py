"""Agent implementation for filoma."""

import os
from dataclasses import dataclass
from typing import Any, List, Optional, Union

from loguru import logger
from pydantic_ai import Agent, RunContext
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

    working_dir: str = os.getcwd()


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
            model: The model string (e.g. 'mistral:mistral-small-latest', 'llama3.1:8b')
                   or a Model instance.
            base_url: Optional base URL for Ollama.
            api_key: Optional API key (required for Mistral).

        """
        self.model = self._resolve_model(model, base_url, api_key)

        self.agent = Agent(
            self.model,
            deps_type=FilomaDeps,
            tools=[
                tools.count_files,
                tools.probe_directory,
                tools.find_duplicates,
                tools.get_file_info,
                tools.search_files,
                tools.get_directory_tree,
                tools.analyze_image,
            ],
        )

        @self.agent.system_prompt
        def add_context(ctx: RunContext[FilomaDeps]) -> str:
            # Build Knowledge Base from docs/guides
            knowledge_base = (
                "FILOMA KNOWLEDGE BASE:\n"
                "- Core Helpers: probe(path), probe_to_df(path), probe_file(path), probe_image(path).\n"
                "- Backends: Rust (fastest), fd (discovery), Python (fallback).\n"
                "- Features: Directory analysis, Polars/Pandas integration, deduplication (exact/text/image), file/image metadata.\n"
            )

            return (
                "You are an expert filesystem analyst using the 'filoma' library. "
                "Your goal is to help users understand their directory structures, "
                "find specific files, and analyze file metadata. "
                "\n\n"
                f"{knowledge_base}\n"
                "\n\n"
                f"CONTEXT: Your current working directory is: {ctx.deps.working_dir}\n"
                "\n\n"
                "CRITICAL INSTRUCTIONS FOR FILE COUNTING:\n"
                "- When the user asks 'how many files' or wants a file count, ALWAYS use the count_files tool.\n"
                "- The count_files tool performs a complete scan of the entire directory tree.\n"
                "- Never use probe_directory for simple file counting - use count_files instead.\n"
                "- Report the exact number from count_files. Do not estimate or modify it.\n"
                "\n\n"
                "CRITICAL INSTRUCTIONS FOR PATH HANDLING:\n"
                "- If the user doesn't specify a directory, DEFAULT to path='.' (the current working directory).\n"
                "- Translate 'this directory', 'here', or '.' to path='.'\n"
                "- Translate 'parent directory' to path='..'\n"
                "- Translate 'home directory' or '~' to path='~'\n"
                "- ALWAYS prefer relative paths (like '.' or './src') when the user is talking about the current context.\n"
                "- ONLY use absolute paths if the user explicitly provided one (e.g., starting with / or C:\\).\n"
                "- NEVER invent or guess absolute paths (e.g., '/home/user/documents', '/this/dir'). "
                "If you are unsure, use path='.' or ask the user for the path.\n"
                "\n\n"
                "CRITICAL INSTRUCTIONS FOR DATA REPORTING:\n"
                "1. When reporting file counts, use the EXACT number from the tool output.\n"
                "2. DO NOT calculate or estimate.\n"
                "3. Be precise and technical.\n"
                "4. Include the comma separator for large numbers (e.g., '77,917' not '77917')."
                "\n\n"
                "CRITICAL INSTRUCTIONS FOR TOOLS:\n"
                "- You ONLY have access to these tools: count_files, probe_directory, find_duplicates, "
                "get_file_info, search_files, get_directory_tree, analyze_image.\n"
                "- search_files: Use 'pattern' for filenames (e.g. 'README.md'), 'extension' for suffixes "
                "without dots (e.g. 'py').\n"
                "- get_directory_tree: Use this to see what's in a folder before deep-diving.\n"
                "- NEVER mention or suggest other tools not in this list. They do not exist.\n"
                "- ALWAYS use a tool call when you need information. Do NOT output raw JSON text in your response; "
                "use the proper tool calling mechanism.\n"
                "- If you cannot do something with the available tools, honestly tell the user it is "
                "outside your current capabilities."
            )

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
            from pydantic_ai.models.openai import OpenAIChatModel

            m_name = env_model or "llama3.1:8b"

            # Check if it's explicitly an Ollama endpoint
            is_ollama = "localhost:11434" in env_base_url or "ollama" in env_base_url

            if is_ollama:
                logger.info(f"Ollama detected: {env_base_url}")
                from pydantic_ai.providers.ollama import OllamaProvider

                # Strip 'ollama:' prefix if present (for consistency with pydantic-ai examples)
                if m_name.startswith("ollama:"):
                    m_name = m_name[7:]  # Remove 'ollama:' prefix

                logger.info(f"Using local Ollama model: {m_name}")

                # Use OllamaProvider for local Ollama
                provider = OllamaProvider(base_url=env_base_url, api_key=env_api_key)
                return OpenAIChatModel(model_name=m_name, provider=provider)

            logger.error(f"Unsupported provider URL: {env_base_url}. Filoma Brain only supports Mistral Cloud and local Ollama.")
            raise ValueError(f"Unsupported AI provider: {env_base_url}")

        # Logic: Scenario A (Mistral)
        mistral_key = os.getenv("MISTRAL_API_KEY")
        if mistral_key:
            m_name = env_model or "mistral:mistral-small-latest"
            logger.info(f"Using Mistral AI with model '{m_name}' (MISTRAL_API_KEY found).")
            # If it doesn't have the prefix, add it for pydantic-ai resolution
            if ":" not in m_name:
                m_name = f"mistral:{m_name}"
            return m_name

        # Default Fallback
        logger.warning("No AI configuration found. Defaulting to 'llama3.1:8b'.")
        return "llama3.1:8b"

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
