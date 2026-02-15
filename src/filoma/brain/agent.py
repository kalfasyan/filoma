"""Agent implementation for filoma."""

import os
from dataclasses import dataclass
from typing import Any, List, Optional, Union

from loguru import logger
from pydantic_ai import Agent, ModelSettings, RunContext
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
    current_df: Optional[Any] = None


class FilomaAgent:
    """An intelligent agent for interacting with filoma."""

    API_REFERENCE = """
COMPLETE TOOL LIST (exhaustive - no other operations exist):

1. count_files(path: str = ".") -> str
   Returns a report of total files and folders in path (full recursive scan).

2. probe_directory(path: str = ".", max_depth: int = None, ignore_safety_limits: bool = False) -> str
   Summarizes a directory (top extensions, file/folder counts). Use ignore_safety_limits=True for deep scans of known large dirs.

3. find_duplicates(path: str = ".", ignore_safety_limits: bool = False) -> str
   Finds duplicate files in a directory.

4. get_file_info(path: str) -> str
   Retrieves detailed technical metadata (JSON) for a specific file.

5. search_files(path: str = ".", pattern: str = None, extension: str = None, min_size: str = None) -> str
   Searches for files matching a regex pattern, extension (no dot), or minimum size (e.g., '1M').
   automatically loads results into a DataFrame for further analysis.

6. get_directory_tree(path: str) -> str
   Lists immediate contents (files/folders) of a directory (non-recursive). Good for initial exploration.

7. analyze_image(path: str) -> str
   Performs specialized analysis on an image (shape, dtype, stats).

8. analyze_dataframe(operation: str, **kwargs) -> str
   Perform operations on the currently loaded search results (DataFrame).
   The DataFrame is automatically loaded after running search_files.
   Available operations:

   a) 'filter_by_extension' - Keep only files with specific extension
      Example: analyze_dataframe(operation='filter_by_extension', extension='py')
      Returns: Count of filtered files

   b) 'filter_by_pattern' - Keep only files matching a regex pattern
      Example: analyze_dataframe(operation='filter_by_pattern', pattern='test.*')
      Returns: Count of filtered files

   c) 'sort_by_size' - Sort files by size (small to large or vice versa)
      Example: analyze_dataframe(operation='sort_by_size', ascending=False)
      Returns: Top 10 files with their sizes in human-readable format

   d) 'head' - Show first N rows of the DataFrame
      Example: analyze_dataframe(operation='head', n=10)
      Returns: JSON with paths, sizes, and other metadata for first N files

   e) 'summary' - Get statistics about the DataFrame
      Example: analyze_dataframe(operation='summary')
      Returns: Total count, top extensions, top directories

   Note: Each filter operation updates the DataFrame, so multiple filters can be chained.

9. export_dataframe(path: str, format: str = "csv") -> str
   Exports the current DataFrame to a file (csv, json, or parquet format).
   Example: export_dataframe(path='results.csv', format='csv')
   Supported formats: 'csv', 'json', 'parquet'

10. open_file(path: str) -> str
    Displays the content of a file directly to the user's terminal using 'bat' or 'cat'.
    This is the most efficient way to VIEW a file. The agent DOES NOT see the content.
    Use this when the user asks to "view", "show", "open", or "read" a file for themselves.

11. read_file(path: str, start_line: int = 1, end_line: int = None) -> str
    Reads the content of a file into the agent's context.
    Use this ONLY when you need to ANALYZE the content (e.g., summarize, find bugs, explain code).
    Returns text wrapped in markdown code blocks with line numbers.

12. preview_image(path: str, width: int = 60, mode: str = "ansi") -> str
    Generates a preview of an image. Useful for visual confirmation of image contents.
    Modes: 'ansi' (default) for colored RGB blocks, 'ascii' for grayscale text.
    Works with PNG, JPG, BMP, etc.

13. list_available_tools() -> str
    Returns this API reference. Use this if you are unsure of your capabilities.

IMPORTANT: I CANNOT create, delete, move, rename, or modify files. I am a READ-ONLY analysis tool (except for export_dataframe).
"""

    FEW_SHOT_EXAMPLES = ""

    def __init__(
        self,
        model: Optional[Union[str, Model]] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        """Initialize the FilomaAgent.

        Args:
        ----
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
                tools.list_available_tools,
                tools.analyze_image,
                tools.analyze_dataframe,
                tools.export_dataframe,
                tools.open_file,
                tools.read_file,
                tools.preview_image,
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
                f"{self.API_REFERENCE}\n"
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
                "  1. VIEWING DATA: Use analyze_dataframe(operation='head', n=10) to see file details\n"
                "  2. SORTING: Use analyze_dataframe(operation='sort_by_size', ascending=False) for largest files first\n"
                "  3. FILTERING: Use analyze_dataframe(operation='filter_by_extension', extension='py') to narrow results\n"
                "  4. STATISTICS: Use analyze_dataframe(operation='summary') for counts and breakdowns\n"
                "  5. EXPORTING: Use export_dataframe(path='results.csv') to save results\n"
                "- CHAINING OPERATIONS: Each filter operation updates the DataFrame, so you can:\n"
                "  Step 1: search_files(extension='md')\n"
                "  Step 2: analyze_dataframe(operation='sort_by_size', ascending=False)\n"
                "  Step 3: analyze_dataframe(operation='head', n=5) to see top 5 largest .md files\n"
                "- FOLLOW-UP REQUESTS: When a user makes a follow-up request about results from a previous search:\n"
                "  * For 'show paths' or 'list them': Use analyze_dataframe(operation='head', n=20)\n"
                "  * For 'show sizes': Use analyze_dataframe(operation='sort_by_size')\n"
                "  * For 'largest files': Use analyze_dataframe(operation='sort_by_size', ascending=False)\n"
                "  * NEVER output tool call JSON as plain text. Always use the actual tool calling mechanism.\n"
                "  * If the dataframe is already loaded from a previous search, use it instead of searching again.\n"
                "- EXECUTE ONE TOOL AT A TIME. Do not output multiple tool calls in one message.\n"
                "- Wait for the result of one operation before calling the next."
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

        # Logic: Scenario A (Google Gemini)
        gemini_key = os.getenv("GEMINI_API_KEY")
        if gemini_key:
            m_name = env_model or "gemini-1.5-flash"
            logger.info(f"Using Google Gemini with model '{m_name}' (GEMINI_API_KEY found).")

            from pydantic_ai.models.google import GoogleModel

            # GoogleModel automatically uses GEMINI_API_KEY from environment
            return GoogleModel(model_name=m_name)

        # Logic: Scenario B (Mistral)
        mistral_key = os.getenv("MISTRAL_API_KEY")
        if mistral_key:
            m_name = env_model or "mistral:mistral-small-latest"
            logger.info(f"Using Mistral AI with model '{m_name}' (MISTRAL_API_KEY found).")
            # If it doesn't have the prefix, add it for pydantic-ai resolution
            if ":" not in m_name:
                m_name = f"mistral:{m_name}"

            # Mistral via OpenAI-compatible API in pydantic-ai
            from pydantic_ai.models.openai import OpenAIChatModel

            return OpenAIChatModel(model_name=m_name, api_key=mistral_key)

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
