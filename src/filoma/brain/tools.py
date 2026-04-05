"""Tools for the FilomaAgent."""

import json
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, List, Optional, Union

from loguru import logger
from pydantic import BaseModel
from pydantic_ai import RunContext

if TYPE_CHECKING:
    pass

import filoma

from .models import AuditFinding, AuditReport, HygieneMetric, HygieneReport, MigrationReadinessItem, MigrationReadinessReport


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
        return f"Error generating image preview: {str(e)}"


def audit_corrupted_files(ctx: RunContext[Any], path: str) -> str:
    """Perform a corrupted file audit and return a structured report.

    This tool checks for zero-byte files, corrupt images, and other integrity issues.

    Args:
        ctx: The run context.
        path: Path to the directory to audit.

    Returns:
        JSON-formatted audit report with findings and recommendations.

    """
    start_time = time.time()
    try:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return f"Error: Path '{path}' does not exist."

        from filoma.core.verifier import DatasetVerifier

        # Run integrity checks
        verifier = DatasetVerifier(str(p))
        results = verifier.check_integrity()

        # Process findings
        findings = []
        failed_files = results.get("failed_files", [])

        for i, issue in enumerate(failed_files):
            file_path = issue.get("path", "")
            reason = issue.get("reason", "unknown")

            severity = "critical" if reason == "corrupt_or_unsupported" else "high"
            description = "Corrupted or unsupported file" if reason == "corrupt_or_unsupported" else "Zero-byte file"
            recommendation = "Remove or repair the file" if reason == "corrupt_or_unsupported" else "Remove or restore the file"

            finding = AuditFinding(
                id=f"corruption-{i+1}",
                severity=severity,
                category="integrity",
                description=description,
                evidence={"file_path": file_path, "issue_type": reason},
                confidence=0.95,
                recommendation=recommendation,
                affected_paths=[file_path]
            )
            findings.append(finding)

        # Create summary
        summary = {
            "total_files_checked": len(failed_files),
            "corrupted_files": len([f for f in failed_files if f.get("reason") == "corrupt_or_unsupported"]),
            "zero_byte_files": len([f for f in failed_files if f.get("reason") == "zero_byte"]),
            "success_rate": 1.0 - (len(failed_files) / max(len(failed_files) + 1, 1))  # Avoid division by zero
        }

        # Create report
        report = AuditReport(
            report_id=str(uuid.uuid4()),
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            target_path=str(p),
            status="completed",
            summary=summary,
            findings=findings,
            execution_time_seconds=time.time() - start_time,
            tool_versions={"filoma": "1.11.11", "verifier": "1.0"}
        )

        return f"CORRUPTED FILE AUDIT REPORT:\n{report.model_dump_json(indent=2)}"

    except Exception as e:
        report = AuditReport(
            report_id=str(uuid.uuid4()),
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            target_path=path,
            status="failed",
            summary={"error": str(e)},
            findings=[],
            execution_time_seconds=time.time() - start_time,
            tool_versions={"filoma": "1.11.11"}
        )
        return f"CORRUPTED FILE AUDIT REPORT (FAILED):\n{report.model_dump_json(indent=2)}"


def generate_hygiene_report(ctx: RunContext[Any], path: str) -> str:
    """Generate a dataset hygiene report with quality metrics.

    This tool analyzes dataset quality including duplicates, class balance,
    cross-split leakage, and anomalous files.

    Args:
        ctx: The run context.
        path: Path to the dataset directory.

    Returns:
        JSON-formatted hygiene report with metrics and issues.

    """
    start_time = time.time()
    try:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return f"Error: Path '{path}' does not exist."

        from filoma.core.verifier import DatasetVerifier

        # Run quality checks
        verifier = DatasetVerifier(str(p))
        results = verifier.run_all()

        # Process metrics
        metrics = []

        # Dimension consistency metric
        dims = results.get("dimensions", {})
        if "outlier_percentage" in dims:
            outlier_pct = dims["outlier_percentage"]
            metrics.append(HygieneMetric(
                name="dimension_consistency",
                value=100 - outlier_pct,
                threshold=95.0,
                status="pass" if (100 - outlier_pct) >= 95 else "warn" if (100 - outlier_pct) >= 90 else "fail",
                description="Percentage of images with consistent dimensions"
            ))

        # Duplicate detection metric
        dups = results.get("duplicates", {})
        dup_count = dups.get("duplicate_count", 0)
        metrics.append(HygieneMetric(
            name="duplicate_files",
            value=float(dup_count),
            threshold=0.0,
            status="pass" if dup_count == 0 else "fail",
            description="Number of duplicate file groups detected"
        ))

        # Class balance metric
        balance = results.get("class_balance", {})
        class_dist = balance.get("class_distribution", {})
        if class_dist:
            import statistics
            counts = list(class_dist.values())
            if len(counts) > 1:
                mean_count = statistics.mean(counts)
                std_dev = statistics.stdev(counts) if len(counts) > 1 else 0
                cv = (std_dev / mean_count * 100) if mean_count > 0 else 0  # Coefficient of variation

                metrics.append(HygieneMetric(
                    name="class_balance",
                    value=cv,
                    threshold=30.0,
                    status="pass" if cv <= 30 else "warn" if cv <= 50 else "fail",
                    description="Class distribution coefficient of variation (lower is better)"
                ))

        # Process issues
        issues = []

        # Duplicates as issues
        if dup_count > 0:
            issue = AuditFinding(
                id="hygiene-duplicates",
                severity="high",
                category="quality",
                description=f"Found {dup_count} duplicate file groups",
                evidence={"duplicate_count": dup_count, "duplicates": dups.get("duplicates", [])[:5]},  # Limit evidence
                confidence=0.9,
                recommendation="Remove duplicate files to improve dataset quality",
                affected_paths=[]
            )
            issues.append(issue)

        # Calculate overall score (simple average of metric statuses)
        score_components = []
        for metric in metrics:
            if metric.status == "pass":
                score_components.append(100.0)
            elif metric.status == "warn":
                score_components.append(70.0)
            else:  # fail
                score_components.append(30.0)

        overall_score = statistics.mean(score_components) if score_components else 100.0

        # Recommendations
        recommendations = []
        if dup_count > 0:
            recommendations.append("Remove duplicate files to improve dataset quality")
        if any(m.status == "fail" for m in metrics):
            recommendations.append("Address failed quality metrics to improve dataset hygiene")

        # Create report
        report = HygieneReport(
            report_id=str(uuid.uuid4()),
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            target_path=str(p),
            status="completed",
            overall_score=overall_score,
            metrics=metrics,
            issues=issues,
            recommendations=recommendations,
            execution_time_seconds=time.time() - start_time
        )

        return f"DATASET HYGIENE REPORT:\n{report.model_dump_json(indent=2)}"

    except Exception as e:
        report = HygieneReport(
            report_id=str(uuid.uuid4()),
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            target_path=path,
            status="failed",
            overall_score=0.0,
            metrics=[],
            issues=[],
            recommendations=[f"Failed to generate report: {str(e)}"],
            execution_time_seconds=time.time() - start_time
        )
        return f"DATASET HYGIENE REPORT (FAILED):\n{report.model_dump_json(indent=2)}"


def assess_migration_readiness(ctx: RunContext[Any], path: str) -> str:
    """Assess dataset migration readiness with structured analysis.

    Evaluates dataset stability, structure, and readiness for migration.

    Args:
        ctx: The run context.
        path: Path to the dataset directory.

    Returns:
        JSON-formatted migration readiness report.

    """
    start_time = time.time()
    try:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return f"Error: Path '{path}' does not exist."

        from filoma.core.verifier import DatasetVerifier
        from filoma.dataset import Dataset

        # Check basic dataset structure
        dataset = Dataset(str(p))

        # Run verification to check integrity
        verifier = DatasetVerifier(str(p))
        integrity_results = verifier.check_integrity()

        # Items evaluation
        items = []
        blockers = []
        risks = []

        # Check for corrupted files (blocker)
        failed_files = integrity_results.get("failed_files", [])
        if failed_files:
            blockers.append(f"Dataset contains {len(failed_files)} corrupted or zero-byte files")
            item = MigrationReadinessItem(
                id="integrity-corruption",
                category="data",
                status="blocked",
                description=f"Dataset contains {len(failed_files)} corrupted or zero-byte files",
                priority="high",
                dependencies=[],
                estimated_effort_hours=len(failed_files) * 0.1
            )
            items.append(item)
        else:
            item = MigrationReadinessItem(
                id="integrity-ok",
                category="data",
                status="ready",
                description="No corrupted or zero-byte files detected",
                priority="low",
                dependencies=[],
                estimated_effort_hours=0.0
            )
            items.append(item)

        # Check file distribution (structure)
        try:
            df = dataset.to_dataframe(enrich=False)
            total_files = len(df)

            if total_files == 0:
                blockers.append("Dataset is empty")
                item = MigrationReadinessItem(
                    id="structure-empty",
                    category="structure",
                    status="blocked",
                    description="Dataset is empty",
                    priority="high",
                    dependencies=[],
                    estimated_effort_hours=0.0
                )
                items.append(item)
            else:
                item = MigrationReadinessItem(
                    id="structure-populated",
                    category="structure",
                    status="ready",
                    description=f"Dataset contains {total_files:,} files",
                    priority="low",
                    dependencies=[],
                    estimated_effort_hours=0.0
                )
                items.append(item)

                # Check extension variety
                try:
                    ext_counts = df.extension_counts().to_dict()
                    unique_extensions = len(ext_counts)
                    item = MigrationReadinessItem(
                        id="structure-diversity",
                        category="structure",
                        status="ready" if unique_extensions > 1 else "warning",
                        description=f"Dataset contains {unique_extensions} file types",
                        priority="medium",
                        dependencies=[],
                        estimated_effort_hours=0.0
                    )
                    items.append(item)
                except Exception:
                    pass  # Skip if extension analysis fails

        except Exception as e:
            risks.append(f"Unable to analyze dataset structure: {str(e)}")

        # Estimate migration time (simplified model)
        estimated_time = max(0.1, total_files * 0.0001) if 'total_files' in locals() else 1.0

        # Overall readiness calculation
        blocked_items = len([i for i in items if i.status == "blocked"])
        warning_items = len([i for i in items if i.status == "warning"])

        if blocked_items > 0:
            overall_readiness = 0.0
        elif warning_items > 0:
            overall_readiness = 50.0
        else:
            overall_readiness = 100.0

        # Recommendations
        recommendations = []
        if blocked_items > 0:
            recommendations.append("Fix blocker issues before migration")
        if warning_items > 0:
            recommendations.append("Address warnings to improve migration success probability")
        if overall_readiness >= 80:
            recommendations.append("Dataset appears ready for migration")

        # Create report
        report = MigrationReadinessReport(
            report_id=str(uuid.uuid4()),
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            target_path=str(p),
            status="completed" if blocked_items == 0 else "partial",
            overall_readiness=overall_readiness,
            items=items,
            blockers=blockers,
            risks=risks,
            recommendations=recommendations,
            estimated_migration_time_hours=estimated_time,
            execution_time_seconds=time.time() - start_time
        )

        return f"MIGRATION READINESS REPORT:\n{report.model_dump_json(indent=2)}"

    except Exception as e:
        report = MigrationReadinessReport(
            report_id=str(uuid.uuid4()),
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            target_path=path,
            status="failed",
            overall_readiness=0.0,
            items=[],
            blockers=[f"Failed to assess migration readiness: {str(e)}"],
            risks=[],
            recommendations=["Fix the error and retry the assessment"],
            estimated_migration_time_hours=0.0,
            execution_time_seconds=time.time() - start_time
        )
        return f"MIGRATION READINESS REPORT (FAILED):\n{report.model_dump_json(indent=2)}"

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

        report = (
            f"DUPLICATE REPORT FOR: {p}\n"
            f"--------------------------------------------------\n"
            f"TOTAL DUPLICATE FILES FOUND: {exact_count}\n"
            f"NUMBER OF DUPLICATE GROUPS: {len(exact_groups)}\n"
            f"--------------------------------------------------\n"
        )

        for i, group in enumerate(exact_groups):
            report += f"\nGroup {i + 1}:\n"
            for file_path in group:
                report += f"  - {file_path}\n"

        return report

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


def verify_integrity(ctx: RunContext[Any], reference: str, target: str) -> str:
    """Verify dataset integrity using snapshots or manifests."""
    from filoma.core.verifier import verify_dataset

    try:
        results = verify_dataset(reference, target_path=target)
        return f"INTEGRITY CHECK RESULTS:\n{results}"
    except Exception as e:
        return f"Error during verification: {str(e)}"


def run_quality_check(ctx: RunContext[Any], path: str) -> str:
    """Run data quality analysis on a dataset."""
    from filoma.core.verifier import DatasetVerifier

    try:
        verifier = DatasetVerifier(path)
        verifier.run_all()
        # Capture the output of print_summary
        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            verifier.print_summary()
        return f"QUALITY CHECK RESULTS:\n{f.getvalue()}"
    except Exception as e:
        return f"Error during quality checks: {str(e)}"


def filter_by_extension(ctx: RunContext[Any], extensions: Union[str, List[str]]) -> str:
    """Filter the current DataFrame to only include files with specific extensions.

    Args:
    ----
        ctx: The run context.
        extensions: File extension(s) to filter by (e.g., 'jpg', '.py', ['png', 'jpg']).

    """
    if ctx.deps.current_df is None:
        return "Error: No DataFrame loaded. Please run 'search_files' or 'create_dataset_dataframe' first."

    # Lazy import to avoid recursive dependencies
    df = ctx.deps.current_df
    try:
        if not extensions:
            return "Error: 'extensions' argument is required (e.g., 'jpg' or ['py', 'rs'])."

        if isinstance(extensions, str):
            # Split by comma or space if multiple extensions are provided in a string
            import re

            ext_list = re.split(r"[\s,]+", extensions.strip())
            extensions = [e for e in ext_list if e]

        df = df.filter_by_extension(extensions)
        ctx.deps.current_df = df
        return f"✅ Successfully filtered DataFrame to {len(df)} files with extensions: {', '.join(extensions)}"
    except Exception as e:
        return f"Error filtering by extension: {str(e)}"


def filter_by_pattern(ctx: RunContext[Any], pattern: str) -> str:
    """Filter the current DataFrame to only include files matching a regex pattern."""
    if ctx.deps.current_df is None:
        return "Error: No DataFrame loaded. Please run 'search_files' or 'create_dataset_dataframe' first."

    if not pattern:
        return "Error: 'pattern' argument is required."

    df = ctx.deps.current_df
    try:
        df = df.filter_by_pattern(pattern)
        ctx.deps.current_df = df
        return f"✅ Successfully filtered DataFrame to {len(df)} files matching pattern '{pattern}'."
    except Exception as e:
        return f"Error filtering by pattern: {str(e)}"


def sort_dataframe_by_size(ctx: RunContext[Any], ascending: bool = False, top_n: int = 10) -> str:
    """Sort the current DataFrame by file size and return a top-N preview."""
    if ctx.deps.current_df is None:
        return "Error: No DataFrame loaded. Please run 'search_files' or 'create_dataset_dataframe' first."

    df = ctx.deps.current_df
    try:
        if "size_bytes" not in df.columns:
            df.enrich(inplace=True)

        df = df.sort("size_bytes", descending=not ascending)
        ctx.deps.current_df = df

        top_n = max(1, min(int(top_n), 100))
        top_df = df.head(top_n).to_dict()
        paths = top_df.get("path", [])
        sizes = top_df.get("size_bytes", [])

        report = f"Sorted DataFrame by size ({'ascending' if ascending else 'descending'}). Top {len(paths)} files:\n"
        for p, s in zip(paths, sizes):
            size_str = f"{s / 1024 / 1024:.2f} MB" if s > 1024 * 1024 else f"{s / 1024:.2f} KB"
            report += f"- {p} ({size_str})\n"
        return report
    except Exception as e:
        return f"Error sorting dataframe by size: {str(e)}"


def dataframe_head(ctx: RunContext[Any], n: int = 5) -> str:
    """Show the first N rows from the current DataFrame."""
    if ctx.deps.current_df is None:
        return "Error: No DataFrame loaded. Please run 'search_files' or 'create_dataset_dataframe' first."

    df = ctx.deps.current_df
    try:
        n = max(1, min(int(n), 200))
        head_df = df.head(n)
        data = head_df.to_dict()
        return f"First {n} rows:\n{json.dumps(data, indent=2, default=str)}"
    except Exception as e:
        return f"Error retrieving dataframe head: {str(e)}"


def summarize_dataframe(ctx: RunContext[Any]) -> str:
    """Get summary statistics about the current DataFrame."""
    if ctx.deps.current_df is None:
        return "Error: No DataFrame loaded. Please run 'search_files' or 'create_dataset_dataframe' first."

    df = ctx.deps.current_df
    try:
        count = len(df)
        ext_counts = df.extension_counts().head(10).to_dict()

        try:
            dir_counts = df.directory_counts().head(10).to_dict()
        except Exception:
            dir_counts = "N/A"

        summary = {
            "total_files": count,
            "top_extensions": ext_counts,
            "top_directories": dir_counts,
        }
        return f"DataFrame Summary:\n{json.dumps(summary, indent=2)}"
    except Exception as e:
        return f"Error summarizing dataframe: {str(e)}"


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

        # LOAD INTO DATAFRAME (even if empty)
        from filoma.dataframe import DataFrame

        # Create DataFrame from results (empty list is valid)
        df = DataFrame({"path": results})
        
        # Only return early message if no results, but still set the DataFrame
        if not results:
            ctx.deps.current_df = df
            return f"No files found matching the criteria in '{p}'.\n\n✅ Empty DataFrame initialized. You can use other tools when files are found."
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

        report += "\n\n✅ Results loaded into DataFrame. You can now use tools like 'filter_by_extension', 'filter_by_pattern', 'sort_dataframe_by_size', and 'summarize_dataframe'."  # noqa: E501

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
    """Legacy dataframe operation router kept for backward compatibility.

    Prefer using dedicated tools directly:
    - filter_by_extension
    - filter_by_pattern
    - sort_dataframe_by_size
    - dataframe_head
    - summarize_dataframe
    """
    operation = (operation or "").strip().lower()
    if operation == "filter_by_extension":
        ext = kwargs.get("extension") or kwargs.get("extensions")
        return filter_by_extension(ctx, ext)
    if operation == "filter_by_pattern":
        return filter_by_pattern(ctx, kwargs.get("pattern"))
    if operation in {"sort_by_size", "sort_dataframe_by_size"}:
        return sort_dataframe_by_size(ctx, ascending=bool(kwargs.get("ascending", False)), top_n=int(kwargs.get("top_n", 10)))
    if operation in {"head", "dataframe_head"}:
        return dataframe_head(ctx, n=int(kwargs.get("n", 5)))
    if operation in {"summary", "summarize_dataframe"}:
        return summarize_dataframe(ctx)

    return (
        f"Error: Unknown operation '{operation}'. "
        "Supported: filter_by_extension, filter_by_pattern, sort_by_size, head, summary. "
        "Prefer using dedicated dataframe tools directly."
    )


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


def create_dataset_dataframe(ctx: RunContext[Any], path: str, enrich: bool = True) -> str:
    """Create a dataframe from a dataset directory and make it available for analysis.

    This tool creates a metadata dataframe from all files in a directory using
    filoma's probe_to_df functionality. The resulting dataframe can be analyzed
    and exported using other tools.

    Args:
        ctx: The run context.
        path: Path to the dataset directory.
        enrich: Whether to enrich the dataframe with additional metadata (default: True).

    Returns:
        Success message with information about the created dataframe.

    """
    try:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return f"Error: Path '{path}' does not exist."

        if not p.is_dir():
            return f"Error: '{path}' is not a directory."

        logger.info(f"Creating dataframe for dataset directory: {p}")

        # Use filoma's probe_to_df to create the dataframe
        df = filoma.probe_to_df(str(p), enrich=enrich)

        # Store the dataframe in context for further analysis
        ctx.deps.current_df = df

        # Get basic information about the dataframe
        row_count = len(df)
        columns = list(df.columns)

        return (
            f"✅ Successfully created dataframe from dataset directory: {p}\n"
            f"📊 DataFrame contains {row_count:,} rows and {len(columns)} columns\n"
            f"📋 Available columns: {', '.join(columns)}\n\n"
            f"You can now use filter_by_extension(), filter_by_pattern(), sort_dataframe_by_size(), "
            f"dataframe_head(), summarize_dataframe(), or export_dataframe()."
        )
    except Exception as e:
        return f"Error creating dataset dataframe: {str(e)}"


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
