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
class FilarakiDeps:
    """Dependencies for the FilarakiAgent."""

    working_dir: str = os.getcwd()
    current_df: Optional[Any] = None


class FilarakiAgent:
    """An intelligent agent for interacting with filoma."""

    API_REFERENCE = """
COMPLETE TOOL LIST (exhaustive - no other operations exist):

1. count_files(path: str = ".") -> str
   Returns total files and folders in path (full recursive scan).

2. list_directory(path: str) -> str
   Lists files/folders (non-recursive, excludes hidden files).

3. list_directory_all(path: str) -> str
   Lists files/folders (non-recursive, includes hidden files).

4. probe_directory(path: str = ".", max_depth: int = None, ignore_safety_limits: bool = False) -> str
   Summarizes a directory with counts and top extensions.

5. find_duplicates(path: str = ".", ignore_safety_limits: bool = False) -> str
   Finds duplicate files and shows duplicate groups.

6. get_file_info(path: str) -> str
   Returns detailed metadata (JSON) for one file.

7. search_files(path: str = ".", pattern: str = None, extension: str = None, min_size: str = None) -> str
   Searches files by regex, extension, or minimum size and loads DataFrame state.

8. get_directory_tree(path: str) -> str
   Compatibility alias for non-recursive directory listing.

9. list_available_tools() -> str
   Returns this API reference.

10. analyze_image(path: str) -> str
    Performs image analysis (shape, dtype, and basic stats).

11. filter_by_extension(extensions: Union[str, List[str]]) -> str
    Filters current DataFrame by extension(s).

12. filter_by_pattern(pattern: str) -> str
    Filters current DataFrame by regex pattern.

13. sort_dataframe_by_size(ascending: bool = False, top_n: int = 10) -> str
    Sorts current DataFrame by size and returns top-N preview.

14. dataframe_head(n: int = 5) -> str
    Shows first N rows of current DataFrame.

15. summarize_dataframe() -> str
    Returns summary stats for current DataFrame.

16. export_dataframe(path: str, format: str = "csv") -> str
    Exports current DataFrame to csv/json/parquet.

17. open_file(path: str) -> str
    Displays file directly to user terminal (bat/cat).

18. read_file(path: str, start_line: int = 1, end_line: int = None) -> str
    Reads file content into agent context.

19. preview_image(path: str, width: int = 60, mode: str = "ansi") -> str
    Displays image preview (ansi/ascii) to user terminal.

20. verify_integrity(reference: str, target: str) -> str
    Verifies dataset integrity using snapshots/manifests.

21. run_quality_check(path: str) -> str
    Runs data quality checks and returns summary output.

22. create_dataset_dataframe(path: str, enrich: bool = True) -> str
    Creates a metadata DataFrame from a directory.

23. audit_corrupted_files(path: str) -> str
    Reports corrupted/zero-byte files with structured findings.

24. generate_hygiene_report(path: str) -> str
    Generates dataset hygiene metrics and recommendations.

25. assess_migration_readiness(path: str) -> str
    Assesses dataset migration readiness with blockers/risks.

26. audit_dataset(path: str, mode: str = "concise", show_evidence: bool = False,
                  export_path: str = None, export_format: str = "json") -> str
    Runs a full dataset audit workflow (corruption + hygiene + readiness).
    Use mode='verbose' for full component reports.
    Use show_evidence=True to include duplicate/corruption examples.
    Use export_path to save a consolidated report (json, md, or html).

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
            deps_type=FilarakiDeps,
            tools=[
                tools.count_files,
                tools.list_directory,
                tools.list_directory_all,
                tools.probe_directory,
                tools.find_duplicates,
                tools.get_file_info,
                tools.search_files,
                tools.get_directory_tree,
                tools.list_available_tools,
                tools.analyze_image,
                tools.filter_by_extension,
                tools.filter_by_pattern,
                tools.sort_dataframe_by_size,
                tools.dataframe_head,
                tools.summarize_dataframe,
                tools.export_dataframe,
                tools.open_file,
                tools.read_file,
                tools.preview_image,
                tools.verify_integrity,
                tools.run_quality_check,
                tools.create_dataset_dataframe,
                tools.audit_corrupted_files,
                tools.generate_hygiene_report,
                tools.assess_migration_readiness,
                tools.audit_dataset,
            ],
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
                "- Wait for the result of one operation before calling the next."
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
        # Check if Ollama is explicitly configured or auto-detect running on localhost
        ollama_base_url = env_base_url
        is_ollama = False

        if ollama_base_url:
            # Explicit configuration provided
            is_ollama = "localhost:11434" in ollama_base_url or "ollama" in ollama_base_url
        else:
            # Auto-detect: Check if Ollama is running on default port
            try:
                import socket

                # Quick check if Ollama is listening on localhost:11434
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

        if is_ollama:
            from pydantic_ai.models.openai import OpenAIChatModel
            from pydantic_ai.providers.ollama import OllamaProvider

            m_name = env_model or "qwen2.5:14b"

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

            m_name = env_model or "mistral:mistral-small-latest"
            logger.info(f"Using Mistral AI with model '{m_name}' (MISTRAL_API_KEY found).")
            # If it doesn't have the prefix, add it for pydantic-ai resolution
            if ":" not in m_name:
                m_name = f"mistral:{m_name}"

            return OpenAIChatModel(model_name=m_name, api_key=mistral_key)

        # SCENARIO 3: Google Gemini (Cloud - Priority 3)
        gemini_key = os.getenv("GEMINI_API_KEY")
        if gemini_key:
            m_name = env_model or "gemini-1.5-flash"
            logger.info(f"Using Google Gemini with model '{m_name}' (GEMINI_API_KEY found).")

            from pydantic_ai.models.google import GoogleModel

            return GoogleModel(model_name=m_name)

        # SCENARIO 4: OpenAI-compatible / Custom Base URL (Priority 4)
        if env_base_url:
            from pydantic_ai.models.openai import OpenAIChatModel

            m_name = env_model or "gpt-4o-mini"
            openai_key = env_api_key or os.getenv("OPENAI_API_KEY")

            logger.info(f"Using OpenAI-compatible API at {env_base_url} with model: {m_name}")
            return OpenAIChatModel(model_name=m_name, api_key=openai_key, base_url=env_base_url)

        # Default Fallback: Ollama with qwen2.5:14b
        logger.warning("No AI configuration found. Defaulting to local Ollama with 'qwen2.5:14b'.")
        logger.warning("Make sure Ollama is running: ollama serve && ollama pull qwen2.5:14b")
        return "qwen2.5:14b"

    async def run(
        self,
        prompt: str,
        deps: Optional[FilarakiDeps] = None,
        message_history: Optional[List[ModelMessage]] = None,
    ) -> Any:
        """Run the agent with a prompt.

        Returns a result object from pydantic-ai.
        """
        if deps is None:
            deps = FilarakiDeps()

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
