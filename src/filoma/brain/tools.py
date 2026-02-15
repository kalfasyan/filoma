"""Tools for the FilomaAgent."""

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, List, Optional

from loguru import logger
from pydantic import BaseModel
from pydantic_ai import RunContext

if TYPE_CHECKING:
    pass

import filoma


class ProbeResult(BaseModel):
    """Result of a directory probe."""

    path: str
    row_count: int
    columns: List[str]
    summary: str


def count_files(ctx: RunContext[Any], path: str) -> str:
    """Count the total number of files in a directory with FULL recursive scan.

    This always scans the entire directory tree without safety limits.
    Uses the Rust backend for complete accuracy.

    Args:
    ----
        ctx: The run context.
        path: The path to the directory to count files in.

    """
    try:
        p = Path(path).expanduser().resolve()

        if not p.exists():
            return f"Error: The path '{path}' (resolved to '{p}') does not exist. Please provide a valid directory path."

        logger.info(f"Starting FULL file count for '{path}' (no depth limit).")

        # Use DirectoryProfiler directly to get the accurate count from Rust backend
        from filoma.directories import DirectoryProfiler, DirectoryProfilerConfig

        config = DirectoryProfilerConfig(build_dataframe=False)  # Don't need df, just the count
        profiler = DirectoryProfiler(config)
        analysis = profiler.probe(str(p), max_depth=None)

        file_count = analysis.summary.get("total_files", 0)
        folder_count = analysis.summary.get("total_folders", 0)

        return (
            f"FILE COUNT REPORT FOR: {p}\n"
            f"{'=' * 50}\n"
            f"TOTAL FILES: {file_count:,}\n"
            f"TOTAL FOLDERS: {folder_count:,}\n"
            f"TOTAL ITEMS: {file_count + folder_count:,}\n"
            f"{'=' * 50}\n"
            f"This is a COMPLETE scan of the entire directory tree."
        )
    except Exception as e:
        return f"Error counting files: {str(e)}"


def probe_directory(
    ctx: RunContext[Any],
    path: str,
    max_depth: Optional[int] = None,
    ignore_safety_limits: bool = False,
) -> str:
    """Probe a directory and return a summary of the findings.

    Args:
    ----
        ctx: The run context.
        path: The path to the directory to probe.
        max_depth: Maximum depth to recurse.
        ignore_safety_limits: If True, allows deep scanning of project-level folders.
                             ONLY set to True if the user explicitly asked for a deep/full scan.

    """
    try:
        p = Path(path).expanduser().resolve()

        if not p.exists():
            return f"Error: The path '{path}' (resolved to '{p}') does not exist. Please provide a valid directory path."

        effective_max_depth = max_depth

        # Apply safety limit if not explicitly ignored
        depth_was_limited = False
        if not ignore_safety_limits and effective_max_depth is None:
            if p == Path.cwd() or p == Path.cwd().parent:
                logger.info(f"Applying safety limit to '{path}' (depth=2).")
                effective_max_depth = 2
                depth_was_limited = True

        # Use DirectoryProfiler to get accurate summary data
        from filoma.directories import DirectoryProfiler, DirectoryProfilerConfig

        config = DirectoryProfilerConfig(build_dataframe=True)
        profiler = DirectoryProfiler(config)
        analysis = profiler.probe(str(p), max_depth=effective_max_depth)

        # Get accurate counts from summary (not DataFrame which may be incomplete)
        file_count = analysis.summary.get("total_files", 0)
        folder_count = analysis.summary.get("total_folders", 0)

        # Get DataFrame for extension analysis
        df = analysis.to_df()
        if df is not None:
            cols = list(df.columns)
            ext_counts_raw = df.extension_counts().head(10).to_dict()
        else:
            cols = []
            ext_counts_raw = {}

        # Build the report
        report = (
            f"REPORT FOR: {p}\n"
            f"--------------------------------------------------\n"
            f"TOTAL FILES FOUND: {file_count}\n"
            f"TOTAL FOLDERS: {folder_count}\n"
            f"--------------------------------------------------\n"
            f"NOTE: The list below shows ONLY the top 10 extensions.\n"
            f"DO NOT SUM THESE NUMBERS. USE THE TOTAL ABOVE.\n\n"
            f"Top Extensions:\n{json.dumps(ext_counts_raw, indent=2)}\n\n"
            f"Metadata Available: {cols}\n"
            f"Scan Depth: {effective_max_depth or 'Unlimited'}"
        )

        # Add a note if depth was limited
        if depth_was_limited:
            report += (
                "\n\nWARNING: This scan was LIMITED to depth=2 as a safety measure.\n"
                "The actual file count may be higher if subdirectories go deeper.\n"
                "Ask the user if they want a FULL SCAN of the entire directory tree."
            )

        return report

    except Exception as e:
        return f"Error probing directory: {str(e)}"


def find_duplicates(ctx: RunContext[Any], path: str, ignore_safety_limits: bool = False) -> str:
    """Find duplicate files in a directory.

    Args:
    ----
        ctx: The run context.
        path: The path to the directory to check for duplicates.
        ignore_safety_limits: If True, allows deep scanning for duplicates.

    """
    try:
        p = Path(path).expanduser().resolve()

        if not p.exists():
            return f"Error: The path '{path}' (resolved to '{p}') does not exist. Please provide a valid directory path."

        max_depth = None
        if not ignore_safety_limits and p == Path.cwd() or p == Path.cwd().parent:
            logger.info(f"Applying safety limit to duplicate search on '{path}' (depth=2).")
            max_depth = 2

        df = filoma.probe_to_df(str(p), max_depth=max_depth)
        dupes = df.evaluate_duplicates(show_table=False)

        exact_groups = dupes.get("exact", [])
        exact_count = sum(len(g) for g in exact_groups) if exact_groups else 0

        return (
            f"DUPLICATE REPORT FOR: {p}\n"
            f"--------------------------------------------------\n"
            f"TOTAL DUPLICATE FILES FOUND: {exact_count}\n"
            f"NUMBER OF DUPLICATE GROUPS: {len(exact_groups)}\n"
            f"--------------------------------------------------"
        )

    except Exception as e:
        return f"Error finding duplicates: {str(e)}"


def get_file_info(ctx: RunContext[Any], path: str) -> str:
    """Get detailed information about a specific file."""
    try:
        p = Path(path).expanduser().resolve()

        if not p.exists():
            return f"Error: The file/path '{path}' (resolved to '{p}') does not exist."

        info = filoma.probe_file(str(p))
        return f"FILE METADATA:\n{json.dumps(info.as_dict(), indent=2)}"
    except Exception as e:
        return f"Error getting file info: {str(e)}"


def search_files(
    ctx: RunContext[Any],
    path: str,
    pattern: Optional[str] = None,
    extension: Optional[str] = None,
    min_size: Optional[str] = None,
    max_depth: Optional[int] = None,
    include_hidden: bool = False,
    ignore_git_files: bool = True,
) -> str:
    r"""Search for files in a directory based on regex pattern, extension, or size.

    Args:
    ----
        ctx: The run context.
        path: The path to search in.
        pattern: Regex pattern to match filenames (e.g., 'README.md', 'test_.*\.py'). Use this for searching specific filenames.
        extension: File extension to filter by (e.g., 'py', 'jpg'). Do NOT include the dot. Do NOT use this for full filenames.
        min_size: Minimum file size (e.g., '1M', '500K').
        max_depth: Maximum depth to search (default is None for unlimited).
        include_hidden: Whether to include hidden files (default False).
        ignore_git_files: Whether to respect .gitignore (default True). Set to False to find ignored files.

    """
    try:
        from filoma.directories import FdFinder

        p = Path(path).expanduser().resolve()
        if not p.exists():
            return f"Error: Path '{path}' does not exist."

        finder = FdFinder()

        # Common options
        common_opts = {
            "path": str(p),
            "max_depth": max_depth,
            "hidden": include_hidden,
            "no_ignore": not ignore_git_files,
            "case_sensitive": False,  # Default to case-insensitive for better UX
        }

        results = []
        if extension:
            # Handle list or single string
            exts = [extension] if isinstance(extension, str) else extension
            results = finder.find_by_extension(exts, **common_opts)
        elif min_size:
            results = finder.find_large_files(min_size=min_size, **common_opts)
        elif pattern:
            results = finder.find_files(pattern=pattern, **common_opts)
        else:
            return "Error: Please provide at least one search criteria (pattern, extension, or min_size)."

        if not results:
            return f"No files found matching the criteria in '{p}'."

        # LOAD INTO DATAFRAME
        from filoma.dataframe import DataFrame

        # Create DataFrame from results
        df = DataFrame({"path": results})
        # Enrich with metadata (size, dates, etc.)
        # Only enrich if result set is reasonable size to avoid long waits
        if len(results) < 10000:
            logger.info(f"Enriching DataFrame with {len(results)} files...")
            df.enrich(inplace=True)

        ctx.deps.current_df = df

        # If few results, use absolute paths for clarity
        use_absolute = len(results) < 20
        if use_absolute:
            results = [str(Path(r).resolve()) for r in results]

        # Limit results for the agent's context
        limited_results = results[:50]
        report = f"SEARCH RESULTS ({len(results)} found, showing top {len(limited_results)}):\n"
        for r in limited_results:
            report += f"- {r}\n"

        if len(results) > 50:
            report += f"\n... and {len(results) - 50} more."

        if use_absolute:
            report += "\nNote: Showing absolute paths because result count is small."

        report += "\n\n✅ Results loaded into DataFrame. You can now use 'analyze_dataframe' to filter, sort, or summarize."

        return report

    except Exception as e:
        return f"Error searching files: {str(e)}"


def get_directory_tree(ctx: RunContext[Any], path: str) -> str:
    """Get a list of files and folders in the immediate directory (non-recursive).

    Args:
    ----
        ctx: The run context.
        path: The path to list.

    """
    try:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return f"Error: Path '{path}' does not exist."
        if not p.is_dir():
            return f"Error: '{path}' is not a directory."

        items = list(p.iterdir())
        # Sort: directories first, then files
        items.sort(key=lambda x: (not x.is_dir(), x.name.lower()))

        report = f"CONTENTS OF: {p}\n"
        report += f"{'-' * 50}\n"

        for item in items:
            prefix = "📁" if item.is_dir() else "📄"
            # Special icons for known types (inspired by CLI)
            if not item.is_dir():
                suffix = item.suffix.lower()
                if suffix in [".png", ".jpg", ".jpeg", ".tif"]:
                    prefix = "🖼️"
                elif suffix in [".py", ".rs", ".js"]:
                    prefix = "💻"
                elif suffix in [".csv", ".json"]:
                    prefix = "📊"

            report += f"{prefix} {item.name}{'/' if item.is_dir() else ''}\n"

        return report

    except Exception as e:
        return f"Error listing directory: {str(e)}"


def list_available_tools(ctx: RunContext[Any]) -> str:
    """List all available tools and their capabilities.

    Use this if you are unsure of what operations are possible.
    """
    # Note: We import FilomaAgent here to avoid circular imports if necessary,
    # but since this is inside tools.py and FilomaAgent is in agent.py
    # which imports tools, we should be careful.
    # However, we can just hardcode or pass it.
    # For now, let's provide a clear manual list to be safe.
    from .agent import FilomaAgent

    return FilomaAgent.API_REFERENCE


def analyze_image(ctx: RunContext[Any], path: str) -> str:
    """Perform specialized analysis on an image file.

    Returns dimensions, dtype, and basic statistics if available.

    Args:
    ----
        ctx: The run context.
        path: Path to the image file.

    """
    try:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return f"Error: Image '{path}' does not exist."

        report = filoma.probe_image(str(p))

        # Build a nice string report
        data = {
            "path": str(p),
            "type": getattr(report, "file_type", "unknown"),
            "shape": getattr(report, "shape", "unknown"),
            "dtype": getattr(report, "dtype", "unknown"),
            "stats": {
                "min": getattr(report, "min", None),
                "max": getattr(report, "max", None),
                "mean": getattr(report, "mean", None),
            },
        }

        return f"IMAGE ANALYSIS REPORT:\n{json.dumps(data, indent=2)}"

    except Exception as e:
        return f"Error analyzing image: {str(e)}"


def analyze_dataframe(ctx: RunContext[Any], operation: str, **kwargs) -> str:
    """Perform operations on the currently loaded search results (DataFrame).

    Operations:
    - 'filter_by_extension' (arg: extension)
    - 'filter_by_pattern' (arg: pattern)
    - 'sort_by_size' (arg: ascending=True/False)
    - 'head' (arg: n)
    - 'summary' (no args) - returns counts by extension and directory

    Args:
    ----
        ctx: The run context.
        operation: The name of the operation to perform.
        **kwargs: Arguments for the operation.

    """
    if ctx.deps.current_df is None:
        return "Error: No DataFrame loaded. Please run 'search_files' first to populate the DataFrame."

    df = ctx.deps.current_df
    try:
        if operation == "filter_by_extension":
            ext = kwargs.get("extension")
            if not ext:
                return "Error: 'extension' argument required for filter_by_extension"
            df = df.filter_by_extension(ext)
            ctx.deps.current_df = df
            return f"Filtered DataFrame to {len(df)} files with extension '{ext}'."

        elif operation == "filter_by_pattern":
            pattern = kwargs.get("pattern")
            if not pattern:
                return "Error: 'pattern' argument required for filter_by_pattern"
            df = df.filter_by_pattern(pattern)
            ctx.deps.current_df = df
            return f"Filtered DataFrame to {len(df)} files matching pattern '{pattern}'."

        elif operation == "sort_by_size":
            ascending = kwargs.get("ascending", False)
            # Check if size_bytes exists (it should if enriched)
            if "size_bytes" not in df.columns:
                df.enrich(inplace=True)

            df = df.sort("size_bytes", descending=not ascending)
            ctx.deps.current_df = df

            # Show top results after sort
            top_n = df.head(10).to_dict()
            paths = top_n.get("path", [])
            sizes = top_n.get("size_bytes", [])

            report = f"Sorted DataFrame by size ({'ascending' if ascending else 'descending'}). Top 10 files:\n"
            for p, s in zip(paths, sizes):
                size_str = f"{s / 1024 / 1024:.2f} MB" if s > 1024 * 1024 else f"{s / 1024:.2f} KB"
                report += f"- {p} ({size_str})\n"
            return report

        elif operation == "head":
            n = int(kwargs.get("n", 5))
            head_df = df.head(n)
            # Convert to dictionary for readable JSON output
            data = head_df.to_dict()
            return f"First {n} rows:\n{json.dumps(data, indent=2, default=str)}"

        elif operation == "summary":
            count = len(df)
            ext_counts = df.extension_counts().head(5).to_dict()

            # Directory counts if possible
            try:
                dir_counts = df.directory_counts().head(5).to_dict()
            except Exception:
                dir_counts = "N/A"

            summary = {
                "total_files": count,
                "top_extensions": ext_counts,
                "top_directories": dir_counts,
            }
            return f"DataFrame Summary:\n{json.dumps(summary, indent=2)}"

        else:
            return f"Error: Unknown operation '{operation}'. Supported: filter_by_extension, filter_by_pattern, sort_by_size, head, summary."

    except Exception as e:
        return f"Error performing dataframe operation: {str(e)}"


def export_dataframe(ctx: RunContext[Any], path: str, format: str = "csv") -> str:
    """Export the current DataFrame to a file.

    Args:
    ----
        ctx: The run context.
        path: Path to save the file.
        format: 'csv', 'json', or 'parquet'.

    """
    if ctx.deps.current_df is None:
        return "Error: No DataFrame loaded. Please run 'search_files' first."

    df = ctx.deps.current_df
    try:
        p = Path(path).expanduser().resolve()

        if format.lower() == "csv":
            df.save_csv(p)
        elif format.lower() == "parquet":
            df.save_parquet(p)
        elif format.lower() == "json":
            # Polars doesn't have direct save_json in wrapper, use to_pandas or internal write_json
            # Filoma DataFrame wrapper doesn't expose save_json, so use internal polars
            df._df.write_json(str(p))
        else:
            return f"Error: Unsupported format '{format}'. Use csv, json, or parquet."

        return f"Successfully exported DataFrame to {p}"

    except Exception as e:
        return f"Error exporting DataFrame: {str(e)}"


def _get_file_icon(path: Path) -> str:
    """Get an appropriate icon for the file type, consistent with the CLI."""
    suffix = path.suffix.lower()
    if suffix in [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".tif", ".zarr"]:
        return "🖼️"
    elif suffix == ".npy":
        return "🔢"
    elif suffix in [".csv", ".json", ".xml", ".yaml", ".yml"]:
        return "📊"
    elif suffix in [".py", ".rs", ".js", ".ts", ".html", ".css"]:
        return "💻"
    elif suffix in [".txt", ".md", ".pdf", ".doc", ".docx"]:
        return "📄"
    elif suffix in [".zip", ".tar", ".gz", ".rar"]:
        return "📦"
    else:
        return "📄"


def open_file(ctx: RunContext[Any], path: str) -> str:
    """Open a file for viewing by the user using 'bat' or 'cat' in a subprocess.

    This displays the content directly to the user's terminal without loading it into the agent's context.
    Use this when the user asks to "view", "show", "open", or "read" a file just for themselves.

    Args:
    ----
        ctx: The run context.
        path: Path to the file.

    """
    import shutil
    import subprocess

    try:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return f"Error: File '{path}' does not exist."
        if not p.is_file():
            return f"Error: '{path}' is a directory, not a file."

        # Check for 'bat' (syntax highlighting) or fallback to 'cat'
        cmd = "bat" if shutil.which("bat") else "cat"

        # Execute subprocess and let it print directly to terminal (inherit stdout/stderr)
        logger.info(f"Opening file with {cmd}: {p}")
        subprocess.run([cmd, str(p)], check=True)

        return f"✅ Content of '{p.name}' displayed to your terminal using '{cmd}'."

    except subprocess.CalledProcessError as e:
        return f"Error opening file with subprocess: {str(e)}"
    except Exception as e:
        return f"Error: {str(e)}"


def read_file(
    ctx: RunContext[Any],
    path: str,
    start_line: int = 1,
    end_line: Optional[int] = None,
    max_chars: int = 100000,
) -> str:
    """Read the content of a file.

    Returns the file content wrapped in a markdown code block with line numbers.
    Automatically handles large files by limiting characters and providing line range options.

    Args:
    ----
        ctx: The run context.
        path: Path to the file.
        start_line: Line number to start reading from (1-indexed).
        end_line: Line number to stop reading at (inclusive).
        max_chars: Maximum number of characters to read to avoid context overflow.

    """
    try:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return f"Error: File '{path}' does not exist."
        if not p.is_file():
            return f"Error: '{path}' is a directory, not a file."

        # Check file size before reading
        file_size = p.stat().st_size
        if file_size > 10 * 1024 * 1024:  # 10MB safety limit for direct read
            return f"Error: File is too large ({file_size / 1024 / 1024:.2f} MB). Please use a more specific tool or read a smaller range."

        try:
            with p.open("r", encoding="utf-8") as f:
                lines = f.readlines()
        except UnicodeDecodeError:
            return f"Error: File '{path}' appears to be a binary file or uses an unsupported encoding. Cannot display text content."

        total_lines = len(lines)
        start = max(0, start_line - 1)
        end = min(total_lines, end_line if end_line is not None else total_lines)

        if start >= total_lines:
            return f"Error: start_line ({start_line}) exceeds total lines in file ({total_lines})."

        selected_lines = lines[start:end]
        content = "".join(selected_lines)

        # Apply character limit
        truncated = False
        if len(content) > max_chars:
            content = content[:max_chars]
            truncated = True

        # Determine file extension for markdown syntax highlighting
        ext = p.suffix.lstrip(".") or ""
        icon = _get_file_icon(p)

        # Build output with line numbers
        output = f"### {icon} {p.name}\n"
        output += f"*Location: `{p}` (Lines {start + 1}-{end} of {total_lines})*\n\n"
        output += f"```{ext}\n"
        for i, line in enumerate(selected_lines):
            # If we truncated by max_chars, we might not show all selected lines
            current_content_so_far = "".join(selected_lines[: i + 1])
            if len(current_content_so_far) > max_chars:
                output += f"{' ' * (len(str(end)) + 2)}... [TRUNCATED DUE TO SIZE] ...\n"
                truncated = True
                break
            line_num = start + i + 1
            output += f"{line_num:>{len(str(end))}} | {line}"
        output += "```\n"

        if truncated:
            output += "\n> 💡 **Note:** Content was truncated due to size limits. Use `start_line`/`end_line` to see other parts of the file."

        return output

    except Exception as e:
        return f"Error reading file: {str(e)}"


def preview_image(ctx: RunContext[Any], path: str, width: int = 60, mode: str = "ansi") -> str:
    """Generate a preview of an image (ASCII or ANSI color blocks).

    Args:
    ----
        ctx: The run context.
        path: Path to the image file.
        width: Width of the preview in characters (default 60).
        mode: 'ansi' for colored block characters (best), or 'ascii' for text-only.

    """
    try:
        from PIL import Image
        from rich.console import Console

        # Instantiate a console for direct output
        console = Console()

        p = Path(path).expanduser().resolve()
        if not p.exists():
            return f"Error: Image '{path}' does not exist."

        img = Image.open(p)
        original_width, original_height = img.size

        if mode.lower() == "ascii":
            # ASCII characters used to represent different brightness levels
            ASCII_CHARS = "@%#*+=-:. "
            aspect_ratio = original_height / original_width
            height = int(width * aspect_ratio * 0.5)
            img_small = img.resize((width, height)).convert("L")
            pixels = img_small.getdata()
            preview_str = ""
            for i, pixel in enumerate(pixels):
                preview_str += ASCII_CHARS[pixel * (len(ASCII_CHARS) - 1) // 255]
                if (i + 1) % width == 0:
                    preview_str += "\n"
            final_preview = f"```text\n{preview_str}```"
        else:
            # ANSI Block Mode (RGB)
            height = int(width * (original_height / original_width))
            img_small = img.resize((width, height)).convert("RGB")
            preview_str = ""

            for y in range(0, height, 2):
                for x in range(width):
                    pixel1 = img_small.getpixel((x, y))
                    r1, g1, b1 = pixel1[:3] if isinstance(pixel1, (tuple, list)) else (pixel1, pixel1, pixel1)

                    if y + 1 < height:
                        pixel2 = img_small.getpixel((x, y + 1))
                        r2, g2, b2 = pixel2[:3] if isinstance(pixel2, (tuple, list)) else (pixel2, pixel2, pixel2)
                    else:
                        r2, g2, b2 = 0, 0, 0

                    # Use Rich's [rgb(r,g,b) on rgb(r,g,b)] markup for robust rendering
                    preview_str += f"[rgb({r1},{g1},{b1}) on rgb({r2},{g2},{b2})]▀[/]"
                preview_str += "\n"
            final_preview = preview_str

        icon = _get_file_icon(p)
        header = f"\n[bold blue]{icon} IMAGE PREVIEW: {p.name}[/bold blue] ({original_width}x{original_height})\n"

        # PRINT DIRECTLY TO TERMINAL
        # highlight=False prevents Rich from trying to apply regex highlighting to our pixels
        console.print(header)
        console.print(final_preview, highlight=False)
        console.print("\n")

        return f"✅ Displayed preview of '{p.name}' directly to user terminal."

    except ImportError:
        return "Error: Pillow and Rich are required for image previews."
    except Exception as e:
        return f"Error generating image preview: {str(e)}"
