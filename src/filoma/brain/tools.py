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
        ctx: The run context.
        path: The path to the directory to count files in.

    """
    try:
        p = Path(path).resolve()
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


def probe_directory(ctx: RunContext[Any], path: str, max_depth: Optional[int] = None, ignore_safety_limits: bool = False) -> str:
    """Probe a directory and return a summary of the findings.

    Args:
        ctx: The run context.
        path: The path to the directory to probe.
        max_depth: Maximum depth to recurse.
        ignore_safety_limits: If True, allows deep scanning of project-level folders.
                             ONLY set to True if the user explicitly asked for a deep/full scan.

    """
    try:
        p = Path(path).resolve()
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
        ctx: The run context.
        path: The path to the directory to check for duplicates.
        ignore_safety_limits: If True, allows deep scanning for duplicates.

    """
    try:
        p = Path(path).resolve()

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
        info = filoma.probe_file(path)
        return f"FILE METADATA:\n{json.dumps(info.as_dict(), indent=2)}"
    except Exception as e:
        return f"Error getting file info: {str(e)}"
