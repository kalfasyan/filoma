"""Agent implementation for filoma."""

import os
from dataclasses import dataclass, field
from typing import Any, List, Optional, Union

from loguru import logger
from pydantic_ai import Agent, ModelSettings, RunContext
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models import Model

# Patch openai models to accept non-standard service_tier values (e.g. 'standard')
# returned by providers like OpenRouter.  Without this, the openai library's Literal
# validation rejects any value outside {'auto','default','flex','scale','priority'}.
try:
    from openai.types.chat.chat_completion import ChatCompletion
    from openai.types.chat.chat_completion_chunk import ChatCompletionChunk

    ChatCompletion.model_fields["service_tier"].annotation = Optional[str]
    ChatCompletion.model_rebuild()
    ChatCompletionChunk.model_fields["service_tier"].annotation = Optional[str]
    ChatCompletionChunk.model_rebuild()
except Exception:
    pass

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    logger.debug("python-dotenv not installed, skipping .env loading")

from filoma.tool_registry import tool_registry


@dataclass
class FilarakiDeps:
    """Dependencies for the FilarakiAgent."""

    working_dir: str = os.getcwd()
    current_df: Optional[Any] = None
    rag_store: Optional[Any] = None
    cached_analyses: dict = field(default_factory=dict)
    cached_dfs: dict = field(default_factory=dict)


class FilarakiAgent:
    """An intelligent agent for interacting with filoma."""

    @staticmethod
    def _build_api_reference() -> str:
        """Build the API reference string from the ToolRegistry."""
        from filoma.tool_registry import tool_registry

        lines = ["COMPLETE TOOL LIST (exhaustive - no other operations exist):", ""]
        for i, spec in enumerate(tool_registry.list_specs(), start=1):
            # Build signature string
            props = spec.param_schema.get("properties", {})
            required = spec.param_schema.get("required", [])
            sig_parts = []
            for pname, pinfo in props.items():
                ptype = pinfo.get("type", "str")
                if pname in required:
                    sig_parts.append(f"{pname}: {ptype}")
                else:
                    sig_parts.append(f"{pname}: {ptype} = None")
            sig = f"{spec.name}({', '.join(sig_parts)}) -> str" if sig_parts else f"{spec.name}() -> str"
            lines.append(f"{i}. {sig}")
            desc = spec.description[:120] if spec.description else ""
            if desc:
                lines.append(f"   {desc}")
        lines.extend(
            [
                "",
                "IMPORTANT: I CANNOT create, delete, move, rename, or modify files. I am a READ-ONLY analysis tool (except for export_dataframe).",
            ]
        )
        return "\n".join(lines)

    FEW_SHOT_EXAMPLES = ""

    def __init__(
        self,
        model: Optional[Union[str, Model]] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        working_dir: Optional[str] = None,
    ):
        """Initialize the FilomaAgent.

        Args:
        ----
            model: The model string (e.g. 'mistral:mistral-small-latest', 'llama3.1:8b')
                   or a Model instance.
            base_url: Optional base URL for Ollama.
            api_key: Optional API key (required for Mistral).
            working_dir: Default working directory for the agent's tools. Defaults to current working directory.

        """
        import filoma.filaraki.tools  # noqa: F401 — triggers @tool_registry.register

        self.model = self._resolve_model(model, base_url, api_key)
        self.default_working_dir = working_dir or os.getcwd()

        self.agent = Agent(
            self.model,
            deps_type=FilarakiDeps,
            tools=[spec.callable for spec in tool_registry.list_specs()],
        )

        @self.agent.system_prompt
        def add_context(ctx: RunContext[FilarakiDeps]) -> str:
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
                f"{self._build_api_reference()}\n"
                "\n\n"
                f"{self.FEW_SHOT_EXAMPLES}\n"
                "\n\n"
                f"CONTEXT: Your current working directory is: {ctx.deps.working_dir}\n"
                "\n\n"
                "CRITICAL INSTRUCTIONS FOR HELP REQUESTS:\n"
                "- When the user asks 'help', 'list tools', 'show tools', 'what can you do', or similar, "
                "ALWAYS call the list_available_tools() tool.\n"
                "- Do NOT respond with generic text. Call the tool to show the complete API reference.\n"
                "\n\n"
                "CRITICAL INSTRUCTIONS FOR FILE COUNTING:\n"
                "- count_files tool: Counts ALL files in a directory (complete recursive scan).\n"
                "  Use ONLY when user asks for total file count without filters.\n"
                "  Examples: 'how many files', 'count all files', 'total files in this directory'\n"
                "- search_files tool: Finds files matching specific criteria (extension, pattern, size).\n"
                "  Use when user wants to count files of a SPECIFIC TYPE.\n"
                "  Examples: 'count .py files', 'how many markdown files', 'list all .txt files'\n"
                "- IMPORTANT: If user asks 'count .py files', use search_files(extension='py') and report the count.\n"
                "  Do NOT use count_files for specific file types - it counts everything.\n"
                "- After search_files runs, the result message tells you how many files were found.\n"
                "  Report that exact number to the user.\n"
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
                "4. Include the comma separator for large numbers (e.g., '77,917' not '77917').\n"
                "5. For count_files output: Look for 'TOTAL FILES:' line and report that number.\n"
                "6. For search_files output: Look for 'X found' or 'X results' and report that number.\n"
                "7. Always include the actual number in your response, not just a vague reference.\n"
                "\n\n"
                "CRITICAL INSTRUCTIONS FOR TOOLS:\n"
                "- You ONLY have access to the tools listed in the COMPLETE TOOL LIST above.\n"
                "- ALWAYS use a tool call when you need information. Do NOT output raw JSON text in your response; "
                "use the proper tool calling mechanism.\n"
                "- IMPORTANT: When you want to call a tool, use the tool calling feature provided by your interface.\n"
                "- DO NOT write tool calls as JSON text strings in your response. This will not execute the tool.\n"
                '- Example of WRONG behavior: Outputting \'{"name": "search_files", ...}\' as text.\n'
                "- Example of CORRECT behavior: Actually calling the search_files tool through the tool calling mechanism.\n"
                "- If you cannot do something with the available tools, honestly tell the user it is "
                "outside your current capabilities."
                "\n\n"
                "CRITICAL INSTRUCTIONS FOR OUTPUT VISIBILITY:\n"
                "- The user CANNOT see the direct output of the tools. They only see your final response.\n"
                "- You MUST explicitly list the results found by the tools in your response.\n"
                "- Do NOT say 'as listed above' or 'see the output' unless you have repeated the information in your message.\n"
                "- When listing files, provide the actual filenames from the search results."
                "\n\n"
                "CRITICAL INSTRUCTIONS FOR DATAFRAME WORKFLOWS:\n"
                "- VIEWING VS ANALYZING FILES:\n"
                "  1. VIEWING: If the user wants to see/view/open a file, ALWAYS use open_file(path). "
                "It uses a local subprocess (bat/cat) to show it to the user directly. This is fast and saves energy.\n"
                "  2. ANALYZING: If the user asks for a summary, explanation, or specific information FROM a file, "
                "use read_file(path) so you can actually see the content.\n"
                "- IMAGE PREVIEWS: Use preview_image(path) to show a colored RGB preview of an image directly to the user.\n"
                "  The preview is displayed in the user's terminal, not in your text response.\n"
                "  After calling preview_image, simply confirm that the preview has been displayed.\n"
                "- WHEN DATAFRAME IS LOADED: After running search_files, a DataFrame is automatically loaded with file metadata.\n"
                "- WHAT THE DATAFRAME CONTAINS: Paths, sizes, extensions, modification dates, and other file properties.\n"
                "- HOW TO USE IT:\n"
                "  1. VIEWING DATA: Use dataframe_head(n=10) to see file details\n"
                "  2. SORTING: Use sort_dataframe_by_size(ascending=False) for largest files first\n"
                "  3. FILTERING: Use filter_by_extension(extensions='py') or filter_by_pattern(pattern='.*test.*')\n"
                "  4. STATISTICS: Use summarize_dataframe() for counts and breakdowns\n"
                "  5. EXPORTING: Use export_dataframe(path='results.csv') to save results\n"
                "- CHAINING OPERATIONS: Each filter operation updates the DataFrame, so you can:\n"
                "  Step 1: search_files(extension='md')\n"
                "  Step 2: filter_by_extension(extensions='md')\n"
                "  Step 3: sort_dataframe_by_size(ascending=False)\n"
                "  Step 4: dataframe_head(n=5) to see top 5 largest .md files\n"
                "- FOLLOW-UP REQUESTS: When a user makes a follow-up request about results from a previous search:\n"
                "  * For 'show paths' or 'list them': Use dataframe_head(n=20)\n"
                "  * For 'show sizes': Use sort_dataframe_by_size()\n"
                "  * For 'largest files': Use sort_dataframe_by_size(ascending=False)\n"
                "  * NEVER output tool call JSON as plain text. Always use the actual tool calling mechanism.\n"
                "  * If the dataframe is already loaded from a previous search, use it instead of searching again.\n"
                "- EXECUTE ONE TOOL AT A TIME. Do not output multiple tool calls in one message.\n"
                "- Wait for the result of one operation before calling the next.\n"
                "\n\n"
                "CRITICAL INSTRUCTIONS FOR RAG (SEMANTIC SEARCH):\n"
                "- When the user asks content-based questions about text files, documentation, or code,\n"
                "  use the RAG tools: first call index_for_rag(path) to index the directory,\n"
                "  then call search_rag(query) to find semantically relevant chunks.\n"
                "- Only index a directory once per session; the RAG store is cached.\n"
                "- Always call search_rag BEFORE answering content questions about indexed files.\n"
                "\n\n"
                "CRITICAL INSTRUCTIONS FOR SCHEMA PROPOSAL:\n"
                "- When asked to propose a dataset schema, pipeline configuration, or quality gates:\n"
                "  1. Use probe_directory(path) to get an overview of the dataset.\n"
                "  2. Use read_file(path) to inspect sample files.\n"
                "  3. Propose: dataset_name, columns (name, dtype, nullable, description),\n"
                "     pipeline_config suggestions, quality_gates thresholds, issues found, and recommendations.\n"
                "  4. Return the proposal in a structured format with clear section headers.\n"
                "- Use markdown tables for column definitions when possible.\n"
                "\n\n"
                "CRITICAL INSTRUCTIONS FOR CLEANUP SCRIPTS:\n"
                "- When duplicate files, data leakage, or class imbalance is detected:\n"
                "  1. Generate a standalone, reviewable Python script with inline comments.\n"
                "  2. Include --dry-run flags and safety checks in all generated scripts.\n"
                "  3. NEVER execute the generated script — present it to the user for review.\n"
                "  4. Use .remove(), .rename(), or shutil.move() with explicit user confirmation prompts.\n"
                "  5. The script must include a docstring explaining what it does and all safety precautions.\n"
            )

    def _resolve_model(
        self,
        model: Optional[Union[str, Model]],
        base_url: Optional[str],
        api_key: Optional[str],
    ) -> Union[str, Model]:
        """Resolve the model name or instance for pydantic-ai.

        Priority order:
        1. Ollama (Local - Privacy First, default)
        2. Mistral AI (Cloud)
        3. Google Gemini (Cloud)
        4. OpenAI-compatible (Generic)
        """
        if model and not isinstance(model, str):
            return model

        # Environment variables
        env_base_url = base_url or os.getenv("FILOMA_FILARAKI_BASE_URL")
        env_model = model or os.getenv("FILOMA_FILARAKI_MODEL")
        env_api_key = api_key or os.getenv("FILOMA_FILARAKI_API_KEY")

        # SCENARIO 1: Ollama (Local - Priority 1)
        # Check if Ollama is explicitly configured or auto-detect running on localhost.
        # Auto-detection is skipped when another cloud provider is explicitly configured.
        ollama_base_url = env_base_url
        is_ollama = False

        # Detect cloud configuration up-front so we can use it both to skip
        # Ollama auto-detection AND to decide whether ``FILOMA_FILARAKI_MODEL``
        # by itself signals Ollama intent.
        has_cloud_key = any(
            [
                os.getenv("MISTRAL_API_KEY"),
                os.getenv("GEMINI_API_KEY"),
                os.getenv("OPENAI_API_KEY"),
                os.getenv("OPENROUTER_API_KEY"),
            ]
        )

        if ollama_base_url:
            # Explicit configuration provided. Match common Ollama URL shapes:
            # - localhost:11434 (default)
            # - "ollama" anywhere in the URL (e.g. http://ollama:11434)
            # - any host on the default Ollama port :11434 (e.g. WSL host IP)
            is_ollama = "localhost:11434" in ollama_base_url or "ollama" in ollama_base_url or ":11434" in ollama_base_url
        else:
            # Only auto-detect Ollama if no cloud provider API key is configured
            if not has_cloud_key:
                try:
                    import socket

                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(0.5)
                    result = sock.connect_ex(("localhost", 11434))
                    sock.close()

                    if result == 0:
                        ollama_base_url = "http://localhost:11434/v1"
                        is_ollama = True
                        logger.debug("Auto-detected Ollama running on localhost:11434")
                except Exception:
                    pass

            # If FILOMA_FILARAKI_MODEL is set but auto-detection didn't find an
            # Ollama daemon on localhost (common in WSL where the daemon runs
            # on the Windows host), still treat the model as Ollama intent
            # provided no cloud key is configured. Users on non-default hosts
            # should set FILOMA_FILARAKI_BASE_URL explicitly.
            if not is_ollama and env_model and not has_cloud_key and not env_base_url:
                ollama_base_url = "http://localhost:11434/v1"
                is_ollama = True
                logger.debug(f"FILOMA_FILARAKI_MODEL='{env_model}' set with no cloud config; assuming Ollama at {ollama_base_url} (override with FILOMA_FILARAKI_BASE_URL).")

        if is_ollama:
            from pydantic_ai.models.openai import OpenAIChatModel
            from pydantic_ai.providers.ollama import OllamaProvider

            m_name = env_model or "gemma4:e4b"

            # Strip 'ollama:' prefix if present
            if m_name.startswith("ollama:"):
                m_name = m_name[7:]

            logger.info(f"Using local Ollama at {ollama_base_url} with model: {m_name}")

            provider = OllamaProvider(base_url=ollama_base_url, api_key=env_api_key)
            return OpenAIChatModel(model_name=m_name, provider=provider)

        # SCENARIO 2: Mistral AI (Cloud - Priority 2)
        mistral_key = env_api_key or os.getenv("MISTRAL_API_KEY")
        if mistral_key:
            from pydantic_ai.models.openai import OpenAIChatModel
            from pydantic_ai.providers.openai import OpenAIProvider

            m_name = env_model or "mistral:mistral-small-latest"
            logger.info(f"Using Mistral AI with model '{m_name}' (MISTRAL_API_KEY found).")
            # If it doesn't have the prefix, add it for pydantic-ai resolution
            if ":" not in m_name:
                m_name = f"mistral:{m_name}"

            provider = OpenAIProvider(base_url="https://api.mistral.ai/v1", api_key=mistral_key)
            return OpenAIChatModel(model_name=m_name, provider=provider)

        # SCENARIO 3: Google Gemini (Cloud - Priority 3)
        gemini_key = os.getenv("GEMINI_API_KEY")
        if gemini_key:
            m_name = env_model or "gemini-3.1-flash-lite"
            logger.info(f"Using Google Gemini with model '{m_name}' (GEMINI_API_KEY found).")

            from pydantic_ai.models.google import GoogleModel

            return GoogleModel(model_name=m_name)

        # SCENARIO 4: OpenAI-compatible / Custom Base URL (Priority 4)
        if env_base_url:
            from pydantic_ai.models.openai import OpenAIChatModel

            m_name = env_model or "gpt-4o-mini"
            openai_key = env_api_key or os.getenv("OPENAI_API_KEY")

            if "openrouter.ai" in env_base_url:
                from pydantic_ai.providers.openrouter import OpenRouterProvider

                provider = OpenRouterProvider(api_key=openai_key)
                logger.info(f"Using OpenRouter with model: {m_name}")
            else:
                from pydantic_ai.providers.openai import OpenAIProvider

                provider = OpenAIProvider(base_url=env_base_url, api_key=openai_key)
                logger.info(f"Using OpenAI-compatible API at {env_base_url} with model: {m_name}")
            return OpenAIChatModel(model_name=m_name, provider=provider)

        # Default Fallback: Ollama with gemma4:e4b
        # Wrap in OllamaProvider so pydantic-ai doesn't try to parse the model
        # string as ``provider:model`` (which crashed older versions with
        # ``ValueError: Unknown provider: gemma4``).
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.ollama import OllamaProvider

        fallback_url = "http://localhost:11434/v1"
        fallback_model = "gemma4:e4b"
        logger.warning(f"No AI configuration found. Defaulting to local Ollama at {fallback_url} with '{fallback_model}'.")
        logger.warning(f"Make sure Ollama is running: ollama serve && ollama pull {fallback_model}")
        provider = OllamaProvider(base_url=fallback_url, api_key=None)
        return OpenAIChatModel(model_name=fallback_model, provider=provider)

    def run(
        self,
        prompt: str,
        deps: Optional[FilarakiDeps] = None,
        message_history: Optional[List[ModelMessage]] = None,
    ) -> Any:
        """Run the agent synchronously.

        This is a convenience wrapper around :meth:`arun` that uses ``asyncio.run()``
        internally, or uses the existing event loop when already in an async context
        (e.g., Jupyter/IPython). Use :meth:`arun` directly if you want to await it
        explicitly in an async context.

        Args:
            prompt: The user's prompt/question.
            deps: Optional dependencies (uses default_working_dir if None).
            message_history: Optional conversation history for multi-turn dialogues.

        Returns:
            A result object from pydantic-ai.

        """
        import asyncio
        import concurrent.futures

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # No running loop — safe to use asyncio.run()
            return asyncio.run(self.arun(prompt=prompt, deps=deps, message_history=message_history))
        else:
            # Already in an async context (e.g., Jupyter) — run in a thread
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, self.arun(prompt=prompt, deps=deps, message_history=message_history))
                return future.result()

    async def arun(
        self,
        prompt: str,
        deps: Optional[FilarakiDeps] = None,
        message_history: Optional[List[ModelMessage]] = None,
    ) -> Any:
        """Run the agent asynchronously.

        Args:
            prompt: The user's prompt/question.
            deps: Optional dependencies (uses default_working_dir if None).
            message_history: Optional conversation history for multi-turn dialogues.

        Returns:
            A result object from pydantic-ai.

        """
        if deps is None:
            deps = FilarakiDeps(working_dir=self.default_working_dir)

        # Deterministic settings for tool usage
        settings = ModelSettings(temperature=0.1)

        # Simple run - pydantic-ai returns an AgentRunResult
        result = await self.agent.run(
            prompt,
            deps=deps,
            message_history=message_history,
            model_settings=settings,
        )

        # Latest pydantic-ai (v1.58+) stores the final response in .data
        # We ensure it's easily accessible for the caller.
        return result
