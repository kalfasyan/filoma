"""Tools for the FilarakiAgent."""

import json
import os
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, List, Optional, Union

from loguru import logger
from pydantic import BaseModel

if TYPE_CHECKING:
    pass

try:
    from pydantic_ai import RunContext
except ImportError:  # pragma: no cover - exercised via tests/test_core_without_optional_extras.py
    # pydantic-ai ships in the optional "agent" extra. Tool functions are plain
    # callables (``filoma audit`` calls ``audit_dataset(None, ...)`` directly),
    # so a minimal stand-in keeps this module importable without it.
    from typing import Generic, TypeVar

    _DepsT = TypeVar("_DepsT")

    class RunContext(Generic[_DepsT]):  # type: ignore[no-redef]
        """Fallback for ``pydantic_ai.RunContext`` when the "agent" extra is not installed."""


import filoma
from filoma.tool_registry import tool_registry

from .audit_report import render_html_report
from .models import AuditFinding, AuditReport, HygieneMetric, HygieneReport, MigrationReadinessItem, MigrationReadinessReport


class ProbeResult(BaseModel):
    """Result of a directory probe."""

    path: str
    row_count: int
    columns: List[str]
    summary: str


# Safety cap for `add_embedding_cols`: embedding is CPU/model-bound (much
# slower than a stat or hash call per file), so a DataFrame covering an
# entire repo (build artifacts, vendored deps, .git, etc.) can otherwise
# silently try to embed tens of thousands of files. See docs/guides/rag.md.
_EMBED_SAFETY_LIMIT = 500

# Safety cap for `add_image_embedding_cols`: image CLIP embedding decodes
# and runs a vision model per file, which is slower than the text path
# above (especially the larger clip-vit-l14 model) — keep the default cap
# tighter accordingly.
_IMAGE_EMBED_SAFETY_LIMIT = 300

# Cap on how many full duplicate groups (every file path listed) `find_duplicates`
# prints by default. A dataset containing a mirrored/augmented copy of
# itself can have thousands of duplicate groups — listing every file in
# every group can balloon to megabytes of output that's slow and expensive
# for an agent to read, when a handful of directory-pair overlap stats
# (`group_by_directory=True`) usually answers the real question. See
# docs/guides/dedup.md.
_DUPLICATE_GROUPS_DISPLAY_LIMIT = 50

# Minimum overlap_pct (see filoma.dedup.summarize_duplicate_directories) for
# a directory pair to be proactively flagged as a likely near-duplicate/
# mirrored folder in find_duplicates' report header.
_NEAR_DUPLICATE_DIR_OVERLAP_PCT = 90.0


def _is_mcp_stdio_mode() -> bool:
    """Return True when running under MCP stdio transport."""
    return os.getenv("FILOMA_MCP_STDIO", "0") == "1"


def _cached_probe(ctx: RunContext[Any], path: str, max_depth: Optional[int] = None) -> Any:
    """Return a cached DirectoryAnalysis for *path*, probing only once per (path, max_depth)."""
    p = Path(path).expanduser().resolve()
    cache_key = (str(p), max_depth)

    if cache_key in ctx.deps.cached_analyses:
        return ctx.deps.cached_analyses[cache_key]

    from filoma.directories import DirectoryProfiler, DirectoryProfilerConfig

    config = DirectoryProfilerConfig(build_dataframe=True)
    profiler = DirectoryProfiler(config)
    analysis = profiler.probe(str(p), max_depth=max_depth)

    ctx.deps.cached_analyses[cache_key] = analysis
    return analysis


def _cached_probe_to_df(ctx: RunContext[Any], path: str, max_depth: Optional[int] = None, enrich: bool = True) -> Any:
    """Return a cached DataFrame for *path*, probing only once per (path, max_depth, enrich)."""
    p = Path(path).expanduser().resolve()
    cache_key = (str(p), max_depth, enrich)

    if cache_key in ctx.deps.cached_dfs:
        return ctx.deps.cached_dfs[cache_key]

    analysis = _cached_probe(ctx, path, max_depth=max_depth)

    df_wrapper = analysis.to_df()
    if df_wrapper is None:
        raise RuntimeError("DataFrame was not built. Ensure 'polars' is installed.")

    df_wrapper.add_lineage_entry("probe", path=str(p))

    if enrich:
        try:
            df_wrapper = df_wrapper.add_depth_col(str(p)).add_path_components().add_file_stats_cols()
        except Exception:
            pass

    ctx.deps.cached_dfs[cache_key] = df_wrapper
    return df_wrapper


@tool_registry.register
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

        analysis = _cached_probe(ctx, str(p))

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


@tool_registry.register
def audit_corrupted_files(ctx: RunContext[Any], path: str, include_hidden: bool = True) -> str:
    """Perform a corrupted file audit and return a structured report.

    This tool checks for zero-byte files, corrupt images, and other integrity issues.

    Args:
        ctx: The run context.
        path: Path to the directory to audit.
        include_hidden: Whether to include hidden (dot-prefixed) directories
            such as .git, .venv, .pixi in the audit. Defaults to True.

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
        verifier = DatasetVerifier(str(p), include_hidden=include_hidden)
        results = verifier.check_integrity()

        # Derive total scanned files for accurate success-rate semantics
        total_files_checked = 0
        try:
            analysis = _cached_probe(ctx, str(p))
            total_files_checked = int(analysis.summary.get("total_files", 0))
        except Exception:
            # Keep audit resilient even if directory counting fails
            total_files_checked = 0

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
                id=f"corruption-{i + 1}",
                severity=severity,
                category="integrity",
                description=description,
                evidence={"file_path": file_path, "issue_type": reason},
                confidence=0.95,
                recommendation=recommendation,
                affected_paths=[file_path],
            )
            findings.append(finding)

        # Create summary
        failed_count = len(failed_files)
        success_rate = 1.0 if total_files_checked == 0 else 1.0 - (failed_count / total_files_checked)

        summary = {
            "total_files_checked": total_files_checked,
            "corrupted_files": len([f for f in failed_files if f.get("reason") == "corrupt_or_unsupported"]),
            "zero_byte_files": len([f for f in failed_files if f.get("reason") == "zero_byte"]),
            "failed_files": failed_count,
            "success_rate": max(0.0, success_rate),
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
            tool_versions={"filoma": "1.11.11", "verifier": "1.0"},
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
            tool_versions={"filoma": "1.11.11"},
        )
        return f"CORRUPTED FILE AUDIT REPORT (FAILED):\n{report.model_dump_json(indent=2)}"


@tool_registry.register
def generate_hygiene_report(ctx: RunContext[Any], path: str, include_hidden: bool = True) -> str:
    """Generate a dataset hygiene report with quality metrics.

    This tool analyzes dataset quality including duplicates, class balance,
    cross-split leakage, and anomalous files.

    Args:
        ctx: The run context.
        path: Path to the dataset directory.
        include_hidden: Whether to include hidden (dot-prefixed) directories
            such as .git, .venv, .pixi in the report. Defaults to True.

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
        verifier = DatasetVerifier(str(p), include_hidden=include_hidden)
        results = verifier.run_all()

        # Process metrics
        metrics = []

        # Dimension consistency metric
        dims = results.get("dimensions", {})
        if "outlier_percentage" in dims:
            outlier_pct = dims["outlier_percentage"]
            metrics.append(
                HygieneMetric(
                    name="dimension_consistency",
                    value=100 - outlier_pct,
                    threshold=95.0,
                    status="pass" if (100 - outlier_pct) >= 95 else "warn" if (100 - outlier_pct) >= 90 else "fail",
                    description="Percentage of images with consistent dimensions",
                )
            )

        # Duplicate detection metric
        dups = results.get("duplicates", {})
        dup_count = dups.get("duplicate_count", 0)
        metrics.append(HygieneMetric(name="duplicate_files", value=float(dup_count), threshold=0.0, status="pass" if dup_count == 0 else "fail", description="Number of duplicate file groups detected"))

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

                metrics.append(
                    HygieneMetric(
                        name="class_balance", value=cv, threshold=30.0, status="pass" if cv <= 30 else "warn" if cv <= 50 else "fail", description="Class distribution coefficient of variation (lower is better)"
                    )
                )

        # Process issues
        issues = []

        # Duplicates as issues
        if dup_count > 0:
            all_groups = dups.get("duplicates", [])
            duplicate_file_count = int(dups.get("duplicate_file_count", sum(len(g) for g in all_groups if isinstance(g, list))))
            largest_group_size = max((len(g) for g in all_groups if isinstance(g, list)), default=0)

            # Estimate wasted space as size*(n-1) per group, using the first
            # readable file as a size reference. Computed over the FULL group
            # list (not just the small sample below) so it reflects the real
            # dataset, not an arbitrary 5-group slice.
            estimated_space_waste_bytes = 0
            for group in all_groups:
                if not isinstance(group, list) or len(group) < 2:
                    continue
                group_size = 0
                for fp in group:
                    try:
                        group_size = Path(str(fp)).stat().st_size
                        if group_size > 0:
                            break
                    except Exception:
                        continue
                estimated_space_waste_bytes += max(0, len(group) - 1) * group_size

            issue = AuditFinding(
                id="hygiene-duplicates",
                severity="high",
                category="quality",
                description=f"Found {dup_count} duplicate file groups ({duplicate_file_count} files total)",
                evidence={
                    "duplicate_count": dup_count,
                    "duplicate_file_count": duplicate_file_count,
                    "largest_duplicate_group_size": largest_group_size,
                    "estimated_space_waste_bytes": estimated_space_waste_bytes,
                    "duplicates": all_groups[:5],  # Sample only, for display — see the *_count/*_bytes fields above for full-dataset totals.
                },
                confidence=0.9,
                recommendation="Remove duplicate files to improve dataset quality",
                affected_paths=[],
            )
            issues.append(issue)

        # Class-balance issue (always emitted so quality gates can consume the distribution)
        if class_dist:
            issues.append(
                AuditFinding(
                    id="hygiene-class-balance",
                    severity="info",
                    category="quality",
                    description=f"Class distribution across {len(class_dist)} classes",
                    evidence={"class_distribution": class_dist},
                    confidence=0.9,
                    recommendation="Monitor class balance for model training",
                    affected_paths=[],
                )
            )

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
            execution_time_seconds=time.time() - start_time,
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
            execution_time_seconds=time.time() - start_time,
        )
        return f"DATASET HYGIENE REPORT (FAILED):\n{report.model_dump_json(indent=2)}"


@tool_registry.register
def assess_migration_readiness(ctx: RunContext[Any], path: str, include_hidden: bool = True) -> str:
    """Assess dataset migration readiness with structured analysis.

    Evaluates dataset stability, structure, and readiness for migration.

    Args:
        ctx: The run context.
        path: Path to the dataset directory.
        include_hidden: Whether to include hidden (dot-prefixed) directories
            such as .git, .venv, .pixi in the integrity check. Defaults to True.

    Returns:
        JSON-formatted migration readiness report.

    """
    start_time = time.time()
    try:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return f"Error: Path '{path}' does not exist."

        from filoma.core.verifier import DatasetVerifier

        # Run verification to check integrity
        verifier = DatasetVerifier(str(p), include_hidden=include_hidden)
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
                estimated_effort_hours=len(failed_files) * 0.1,
            )
            items.append(item)
        else:
            item = MigrationReadinessItem(id="integrity-ok", category="data", status="ready", description="No corrupted or zero-byte files detected", priority="low", dependencies=[], estimated_effort_hours=0.0)
            items.append(item)

        # Check file distribution (structure)
        try:
            df = _cached_probe_to_df(ctx, str(p), enrich=False)
            total_files = len(df)

            if total_files == 0:
                blockers.append("Dataset is empty")
                item = MigrationReadinessItem(id="structure-empty", category="structure", status="blocked", description="Dataset is empty", priority="high", dependencies=[], estimated_effort_hours=0.0)
                items.append(item)
            else:
                item = MigrationReadinessItem(
                    id="structure-populated", category="structure", status="ready", description=f"Dataset contains {total_files:,} files", priority="low", dependencies=[], estimated_effort_hours=0.0
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
                        estimated_effort_hours=0.0,
                    )
                    items.append(item)
                except Exception:
                    pass  # Skip if extension analysis fails

        except Exception as e:
            risks.append(f"Unable to analyze dataset structure: {str(e)}")

        # Estimate migration time (simplified model)
        estimated_time = max(0.1, total_files * 0.0001) if "total_files" in locals() else 1.0

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
            execution_time_seconds=time.time() - start_time,
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
            execution_time_seconds=time.time() - start_time,
        )
        return f"MIGRATION READINESS REPORT (FAILED):\n{report.model_dump_json(indent=2)}"


def _extract_json_payload(report_text: str) -> Optional[dict[str, Any]]:
    r"""Extract JSON payload from a prefixed report string.

    Expected input format is "TITLE:\n{...json...}".
    Returns None when parsing fails.
    """
    try:
        _, payload = report_text.split("\n", 1)
        return json.loads(payload)
    except Exception:
        return None


@tool_registry.register
def audit_dataset(
    ctx: RunContext[Any],
    path: str,
    mode: str = "concise",
    show_evidence: bool = False,
    export_path: Optional[str] = None,
    export_format: str = "json",
    dataframe: Any = None,
    include_hidden: bool = True,
) -> str:
    """Run a full dataset audit workflow in one call.

    This orchestration tool executes three existing reports in sequence:
    - audit_corrupted_files
    - generate_hygiene_report
    - assess_migration_readiness

    It returns a concise or verbose summary and can optionally export a report.

    When *dataframe* is provided (a pre-computed filoma DataFrame), the
    function skips the internal ``probe_to_df`` call and uses the cached
    frame for extension/split distribution profiling.

    Set *include_hidden* to False to exclude hidden (dot-prefixed)
    directories such as ``.git``, ``.venv``, ``.pixi`` from every stage of
    the audit. Defaults to True (scan everything).
    """
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return f"Error: Path '{path}' does not exist."

    mode = (mode or "concise").strip().lower()
    if mode not in {"concise", "verbose"}:
        return "Error: mode must be either 'concise' or 'verbose'."

    export_format = (export_format or "json").strip().lower()
    if export_format not in {"json", "md", "html"}:
        return "Error: export_format must be either 'json', 'md', or 'html'."

    import re

    corruption_report = audit_corrupted_files(ctx, str(p), include_hidden=include_hidden)
    hygiene_report = generate_hygiene_report(ctx, str(p), include_hidden=include_hidden)
    readiness_report = assess_migration_readiness(ctx, str(p), include_hidden=include_hidden)

    corruption_data = _extract_json_payload(corruption_report)
    hygiene_data = _extract_json_payload(hygiene_report)
    readiness_data = _extract_json_payload(readiness_report)

    corrupted_files = 0
    zero_byte_files = 0
    hygiene_score = None
    readiness_score = None
    blockers = 0
    total_files_checked = 0
    failed_files = 0
    duplicate_groups = 0
    evidence_section: List[str] = []

    # Profile dataset once to capture extension/split distributions for richer reporting.
    profile_total_files = 0
    extension_counts: dict[str, int] = {}
    split_counts: dict[str, int] = {}
    split_labels = {"train", "valid", "test"}

    try:
        if dataframe is not None:
            df = dataframe
        else:
            df = _cached_probe_to_df(ctx, str(p), enrich=False)
        profile_total_files = len(df)

        # Normalize extension_count table to {ext: count}
        ext_dict = df.extension_counts().to_dict()
        keys = ext_dict.get("extension", [])
        vals = ext_dict.get("len", ext_dict.get("count", []))
        if keys and vals and len(keys) == len(vals):
            extension_counts = {str(k): int(v) for k, v in zip(keys, vals)}

        # Build split distribution from relative paths (train/valid/test)
        path_dict = df.to_dict()
        for full_path in path_dict.get("path", []):
            try:
                rel = Path(str(full_path)).resolve().relative_to(p)
                top = rel.parts[0].lower() if rel.parts else ""
                if top in split_labels:
                    split_counts[top] = split_counts.get(top, 0) + 1
            except Exception:
                continue
    except Exception:
        # Keep workflow resilient even if profiling fails
        profile_total_files = 0
        extension_counts = {}
        split_counts = {}

    if corruption_data:
        summary = corruption_data.get("summary", {})
        total_files_checked = int(summary.get("total_files_checked", 0))
        failed_files = int(summary.get("failed_files", 0))
        corrupted_files = int(summary.get("corrupted_files", 0))
        zero_byte_files = int(summary.get("zero_byte_files", 0))

        if show_evidence:
            findings = corruption_data.get("findings", [])[:5]
            if findings:
                evidence_section.append("Corruption findings (up to 5):")
                for finding in findings:
                    evidence = finding.get("evidence", {})
                    fpath = evidence.get("file_path", "unknown")
                    issue = evidence.get("issue_type", "unknown")
                    evidence_section.append(f"- {issue}: {fpath}")

    if hygiene_data:
        hygiene_score = hygiene_data.get("overall_score")
        issues = hygiene_data.get("issues", [])
        for issue in issues:
            if issue.get("id") == "hygiene-duplicates":
                evidence = issue.get("evidence", {})
                duplicate_groups = int(evidence.get("duplicate_count", 0))
                if show_evidence:
                    sample_dupes = evidence.get("duplicates", [])[:3]
                    if sample_dupes:
                        evidence_section.append("Duplicate evidence (up to 3 groups):")
                        for i, group in enumerate(sample_dupes, start=1):
                            group_files = group[:3] if isinstance(group, list) else [str(group)]
                            evidence_section.append(f"- Group {i}: {', '.join(map(str, group_files))}")
                break

    # Duplicate impact metrics — read directly from the hygiene evidence,
    # which `generate_hygiene_report` computes over the FULL duplicate-group
    # list. Do NOT recompute these from `evidence["duplicates"]` here: that
    # field is deliberately truncated to a 5-group display sample, and
    # summing over it would silently under-report (e.g. "10 duplicate files"
    # on a dataset that actually has thousands).
    duplicate_files_total = 0
    largest_duplicate_group_size = 0
    estimated_space_waste_bytes = 0
    if hygiene_data:
        for issue in hygiene_data.get("issues", []):
            if issue.get("id") == "hygiene-duplicates":
                evidence = issue.get("evidence", {})
                duplicate_files_total = int(evidence.get("duplicate_file_count", 0))
                largest_duplicate_group_size = int(evidence.get("largest_duplicate_group_size", 0))
                estimated_space_waste_bytes = int(evidence.get("estimated_space_waste_bytes", 0))
                break

    if readiness_data:
        readiness_score = readiness_data.get("overall_readiness")
        readiness_blockers = readiness_data.get("blockers", [])
        blockers = len(readiness_blockers)
        if show_evidence and readiness_blockers:
            evidence_section.append("Migration blockers:")
            for blocker in readiness_blockers[:5]:
                evidence_section.append(f"- {blocker}")

    # Extract readiness total files from item descriptions where available.
    readiness_total_files = 0
    if readiness_data:
        for item in readiness_data.get("items", []):
            desc = str(item.get("description", ""))
            match = re.search(r"contains\s+([\d,]+)\s+files", desc, flags=re.IGNORECASE)
            if match:
                readiness_total_files = int(match.group(1).replace(",", ""))
                break

    # Reconciliation across stages.
    reconciliation = {
        "files_total_profiled": profile_total_files,
        "files_total_integrity_checked": total_files_checked,
        "files_total_readiness_basis": readiness_total_files,
        "count_delta_profile_vs_integrity": profile_total_files - total_files_checked,
        "count_delta_profile_vs_readiness": profile_total_files - readiness_total_files,
        "status": "ok" if profile_total_files in {0, total_files_checked} and readiness_total_files in {0, profile_total_files} else "warn",
    }

    # Extension shares for quick format composition signal.
    extension_share_pct = {ext: round((cnt / profile_total_files) * 100.0, 2) for ext, cnt in extension_counts.items() if profile_total_files > 0}

    duplicate_ratio_pct = round((duplicate_files_total / profile_total_files) * 100.0, 2) if profile_total_files > 0 else 0.0

    # Stage timing summary to show runtime hotspots.
    stage_timings = {
        "integrity_seconds": (corruption_data or {}).get("execution_time_seconds", 0.0),
        "hygiene_seconds": (hygiene_data or {}).get("execution_time_seconds", 0.0),
        "readiness_seconds": (readiness_data or {}).get("execution_time_seconds", 0.0),
    }
    stage_timings["total_seconds"] = round(
        float(stage_timings["integrity_seconds"]) + float(stage_timings["hygiene_seconds"]) + float(stage_timings["readiness_seconds"]),
        6,
    )

    # Structured continuation guidance.
    next_actions = []
    if duplicate_groups > 0:
        next_actions.append(
            {
                "priority": "high",
                "action": "Review and remove duplicate groups",
                "estimated_effort": f"{duplicate_groups} groups",
                "auto_followup_prompt": "Show all duplicate file paths and suggest deletions that preserve split integrity.",
            }
        )
    if corrupted_files > 0 or zero_byte_files > 0:
        next_actions.append(
            {
                "priority": "critical",
                "action": "Quarantine corrupted/zero-byte files",
                "estimated_effort": f"{corrupted_files + zero_byte_files} files",
                "auto_followup_prompt": "List corrupted and zero-byte files with exact paths.",
            }
        )
    if reconciliation["status"] == "warn":
        next_actions.append(
            {
                "priority": "medium",
                "action": "Investigate file-count mismatch across reports",
                "estimated_effort": "10-20 minutes",
                "auto_followup_prompt": "Explain why file totals differ across profile, integrity, and readiness checks.",
            }
        )
    if not next_actions:
        next_actions.append(
            {
                "priority": "low",
                "action": "Export and archive this audit baseline",
                "estimated_effort": "2 minutes",
                "auto_followup_prompt": "Export this report as markdown and summarize key baseline metrics.",
            }
        )

    limitations = []
    if not extension_counts:
        limitations.append("Extension distribution unavailable due to profiling fallback.")
    if not split_counts:
        limitations.append("Split distribution unavailable (no train/valid/test structure detected).")
    if readiness_total_files == 0:
        limitations.append("Readiness file total could not be extracted from readiness item descriptions.")

    consolidated_report = {
        "workflow": "audit_dataset",
        "version": "1.1",
        "target": str(p),
        "mode": mode,
        "summary": {
            "total_files_checked": total_files_checked,
            "failed_files": failed_files,
            "corrupted_files": corrupted_files,
            "zero_byte_files": zero_byte_files,
            "duplicate_groups": duplicate_groups,
            "duplicate_files_total": duplicate_files_total,
            "duplicate_ratio_pct": duplicate_ratio_pct,
            "largest_duplicate_group_size": largest_duplicate_group_size,
            "estimated_space_waste_bytes": estimated_space_waste_bytes,
            "hygiene_score": hygiene_score,
            "migration_readiness": readiness_score,
            "migration_blockers": blockers,
        },
        "dataset_profile": {
            "files_total_profiled": profile_total_files,
            "extension_counts": extension_counts,
            "extension_share_pct": extension_share_pct,
            "split_counts": split_counts,
        },
        "reconciliation": reconciliation,
        "stage_timings": stage_timings,
        "next_actions": next_actions,
        "limitations": limitations,
        "evidence": evidence_section if show_evidence else [],
        "reports": {
            "corruption": corruption_data,
            "hygiene": hygiene_data,
            "readiness": readiness_data,
        },
    }

    executive = (
        "DATASET AUDIT WORKFLOW SUMMARY:\n"
        f"Target: {p}\n"
        f"- Files checked: {total_files_checked}\n"
        f"- Failed files: {failed_files}\n"
        f"- Corrupted files: {corrupted_files}\n"
        f"- Zero-byte files: {zero_byte_files}\n"
        f"- Duplicate groups: {duplicate_groups}\n"
        f"- Duplicate files total: {duplicate_files_total}\n"
        f"- Duplicate ratio: {duplicate_ratio_pct}%\n"
        f"- Hygiene score: {hygiene_score if hygiene_score is not None else 'unknown'}\n"
        f"- Migration readiness: {readiness_score if readiness_score is not None else 'unknown'}\n"
        f"- Migration blockers: {blockers}\n"
        f"- Extension types observed: {len(extension_counts)}\n"
        f"- Split counts: {split_counts if split_counts else 'not detected'}\n"
        f"- Reconciliation status: {reconciliation['status']}\n"
    )

    export_note = ""
    if export_path:
        out = Path(export_path).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)

        if export_format == "json":
            out.write_text(json.dumps(consolidated_report, indent=2), encoding="utf-8")
        elif export_format == "md":
            md = ["# Dataset Audit Workflow Report", "", executive]
            if show_evidence and evidence_section:
                md.extend(["", "## Evidence", *evidence_section])
            md.extend(
                [
                    "",
                    "## Corruption Report",
                    "```json",
                    json.dumps(corruption_data, indent=2, default=str),
                    "```",
                    "",
                    "## Hygiene Report",
                    "```json",
                    json.dumps(hygiene_data, indent=2, default=str),
                    "```",
                    "",
                    "## Readiness Report",
                    "```json",
                    json.dumps(readiness_data, indent=2, default=str),
                    "```",
                ]
            )
            out.write_text("\n".join(md), encoding="utf-8")
        else:
            # Self-contained HTML report for visual inspection and sharing.
            html_doc = render_html_report(consolidated_report, p, mode)
            out.write_text(html_doc, encoding="utf-8")

        export_note = f"\nReport exported to: {out}"

    if mode == "concise":
        concise = [executive]
        if show_evidence and evidence_section:
            concise.append("Evidence:")
            concise.extend(evidence_section)
        if export_note:
            concise.append(export_note.strip())
        return "\n".join(concise)

    verbose_report = (
        f"{executive}\n"
        + ("Evidence:\n" + "\n".join(evidence_section) + "\n\n" if show_evidence and evidence_section else "")
        + "---\n"
        + f"{corruption_report}\n\n"
        + f"{hygiene_report}\n\n"
        + f"{readiness_report}"
        + export_note
    )
    return verbose_report


@tool_registry.register
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

        # Use cached probe to avoid re-scanning the same directory
        analysis = _cached_probe(ctx, str(p), max_depth=effective_max_depth)

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


@tool_registry.register
def find_duplicates(
    ctx: RunContext[Any],
    path: str,
    ignore_safety_limits: bool = False,
    strategy: str = "exact",
    group_by_directory: bool = False,
) -> str:
    """Find duplicate files in a directory via exact content matching.

    Accepts path, ignore_safety_limits, and strategy.
    strategy is accepted for compatibility but ignored — duplicates are
    always matched by SHA-256 content hash. Only exact (byte-identical)
    matching is computed — the expensive O(n^2) text/image near-duplicate
    detection that `evaluate_duplicates()` can also do is intentionally
    skipped here, since this tool never surfaces those results anyway, and
    on a dataset with thousands of images/text files that extra work can
    turn a fast call into one that never returns.

    For "do I have two near-duplicate/mirrored folders?" questions, pass
    `group_by_directory=True`: instead of listing every individual
    duplicate file (which can be tens of thousands of lines on a dataset
    that contains a mirrored/augmented copy of itself), this returns a
    compact per-directory-pair summary (shared file count + overlap %),
    sized by directory count rather than file count. The default
    (`group_by_directory=False`) report also caps at
    `_DUPLICATE_GROUPS_DISPLAY_LIMIT` groups and always includes a short
    "possible near-duplicate directories" hint up top when the data
    suggests it, so you don't have to ask a follow-up question to find out.

    Args:
    ----
        ctx: The run context.
        path: The path to the directory to check for duplicates.
        ignore_safety_limits: If True, allows deep scanning for duplicates.
        strategy: Ignored — duplicates are always matched by exact hash.
        group_by_directory: If True, return a compact directory-pair
            overlap summary instead of listing every duplicate file.

    """
    try:
        p = Path(path).expanduser().resolve()

        if not p.exists():
            return f"Error: The path '{path}' (resolved to '{p}') does not exist. Please provide a valid directory path."

        max_depth = None
        if not ignore_safety_limits and (p == Path.cwd() or str(p.resolve()) == str(Path.cwd().parent.resolve())):
            logger.info(f"Applying safety limit to duplicate search on '{path}' (depth=2).")
            max_depth = 2

        df = _cached_probe_to_df(ctx, str(p), max_depth=max_depth)
        dupes = df.evaluate_duplicates(show_table=False, mode="exact")

        exact_groups = dupes.get("exact", [])
        exact_count = sum(len(g) for g in exact_groups) if exact_groups else 0

        from filoma.dedup import summarize_duplicate_directories

        if "is_file" in df.columns:
            all_paths = [str(fp) for fp, is_f in zip(df.to_polars()["path"].to_list(), df.to_polars()["is_file"].to_list()) if is_f]
        elif "path" in df.columns:
            all_paths = [str(fp) for fp in df.to_polars()["path"].to_list() if Path(fp).is_file()]
        else:
            all_paths = []
        dir_overlap = summarize_duplicate_directories(exact_groups, all_paths=all_paths, min_shared=2)

        report = (
            f"DUPLICATE REPORT FOR: {p}\n"
            f"--------------------------------------------------\n"
            f"TOTAL DUPLICATE FILES FOUND: {exact_count}\n"
            f"NUMBER OF DUPLICATE GROUPS: {len(exact_groups)}\n"
            f"--------------------------------------------------\n"
        )

        # Proactively surface directory-level overlap — "are these two
        # folders near-duplicates?" is usually the real question behind a
        # large duplicate report.
        strong_overlap = [d for d in dir_overlap if d["shared_files"] >= 3 and (d["overlap_pct"] or 0) >= _NEAR_DUPLICATE_DIR_OVERLAP_PCT]
        if strong_overlap:
            report += "\nPOSSIBLE NEAR-DUPLICATE / MIRRORED DIRECTORIES:\n"
            for d in strong_overlap[:5]:
                pct = f"{d['overlap_pct']}%" if d["overlap_pct"] is not None else "?"
                report += f"  - {d['dir_a']}  <->  {d['dir_b']}: {d['shared_files']:,} shared files ({pct} overlap)\n"
            report += "  (pass group_by_directory=True for the full directory-pair breakdown)\n"
            report += "--------------------------------------------------\n"

        if group_by_directory:
            if not dir_overlap:
                return report + "\nNo directory pairs share 2+ duplicate files."
            report += "\nDIRECTORY-PAIR OVERLAP (sorted by shared files):\n"
            for d in dir_overlap[:_DUPLICATE_GROUPS_DISPLAY_LIMIT]:
                pct = f"{d['overlap_pct']}%" if d["overlap_pct"] is not None else "?"
                report += f"  - {d['dir_a']}  <->  {d['dir_b']}: {d['shared_files']:,} shared files ({pct} overlap)\n"
            if len(dir_overlap) > _DUPLICATE_GROUPS_DISPLAY_LIMIT:
                report += f"  ... and {len(dir_overlap) - _DUPLICATE_GROUPS_DISPLAY_LIMIT:,} more directory pairs.\n"
            return report

        displayed_groups = exact_groups[:_DUPLICATE_GROUPS_DISPLAY_LIMIT]
        for i, group in enumerate(displayed_groups):
            report += f"\nGroup {i + 1}:\n"
            for file_path in group:
                report += f"  - {file_path}\n"

        if len(exact_groups) > _DUPLICATE_GROUPS_DISPLAY_LIMIT:
            report += (
                f"\n... and {len(exact_groups) - _DUPLICATE_GROUPS_DISPLAY_LIMIT:,} more duplicate groups not shown "
                f"(showing the first {_DUPLICATE_GROUPS_DISPLAY_LIMIT}). Re-run with group_by_directory=True for a "
                "compact directory-level summary, or export_dataframe() after add_duplicate_cols() for the full "
                "file-level list."
            )

        return report

    except Exception as e:
        return f"Error finding duplicates: {str(e)}"


@tool_registry.register
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


@tool_registry.register
def verify_integrity(ctx: RunContext[Any], reference: str, target: str) -> str:
    """Verify dataset integrity using snapshots or manifests."""
    from filoma.core.verifier import verify_dataset

    try:
        results = verify_dataset(reference, target_path=target)
        return f"INTEGRITY CHECK RESULTS:\n{results}"
    except Exception as e:
        return f"Error during verification: {str(e)}"


@tool_registry.register
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


@tool_registry.register
def filter_by_extension(ctx: RunContext[Any], extensions: Union[str, List[str]]) -> str:
    """Filter the current DataFrame to only include files with specific extensions.

    Args:
    ----
        ctx: The run context.
        extensions: File extension(s) to filter by (e.g., 'jpg', '.py', ['png', 'jpg']).

    """
    if ctx.deps.current_df is None:
        return "Error: No DataFrame loaded. Please run 'search_files' or 'create_dataset_dataframe' first."

    df = ctx.deps.current_df
    try:
        if not extensions:
            return "Error: 'extensions' argument is required (e.g., 'jpg' or ['py', 'rs'])."

        if len(df) == 0:
            return "The current DataFrame already has 0 rows, so there is nothing to filter. Call create_dataset_dataframe() or search_files() again to load data first."

        if isinstance(extensions, str):
            stripped = extensions.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                # Some MCP clients JSON-encode a real array argument as a
                # string when they can't tell from the schema that an array
                # is accepted. Recover the real list instead of letting the
                # comma/whitespace split below treat the brackets and quotes
                # as part of one bogus extension (which would silently match
                # zero files).
                try:
                    parsed = json.loads(stripped)
                    if isinstance(parsed, list):
                        extensions = [str(e) for e in parsed]
                except (json.JSONDecodeError, TypeError):
                    pass

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


@tool_registry.register
def filter_by_pattern(ctx: RunContext[Any], pattern: str) -> str:
    r"""Filter the current DataFrame by a regex (not glob) pattern, e.g. '\.md$' not '*.md'."""
    if ctx.deps.current_df is None:
        return "Error: No DataFrame loaded. Please run 'search_files' or 'create_dataset_dataframe' first."

    if not pattern:
        return "Error: 'pattern' argument is required."

    df = ctx.deps.current_df
    if len(df) == 0:
        return "The current DataFrame already has 0 rows, so there is nothing to filter. Call create_dataset_dataframe() or search_files() again to load data first."

    try:
        df = df.filter_by_pattern(pattern)
        ctx.deps.current_df = df
        return f"✅ Successfully filtered DataFrame to {len(df)} files matching pattern '{pattern}'."
    except Exception as e:
        return f"Error filtering by pattern: {str(e)}"


@tool_registry.register
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


@tool_registry.register
def add_duplicate_cols(ctx: RunContext[Any]) -> str:
    """Flag exact duplicate rows in the current DataFrame by content hash (sha256).

    Adds `is_exact_duplicate` (bool) and `exact_dup_group_id` (str) columns
    so duplicates can be filtered/queried like any other column. Computes
    sha256 hashes first if not already present \u2014 this reads every file's
    full content and can be slow on large datasets.
    """
    if ctx.deps.current_df is None:
        return "Error: No DataFrame loaded. Please run 'search_files' or 'create_dataset_dataframe' first."

    df = ctx.deps.current_df
    try:
        df = df.add_duplicate_cols()
        ctx.deps.current_df = df
        dup_count = int(df.to_polars()["is_exact_duplicate"].sum())
        return f"\u2705 Flagged exact duplicates: {dup_count} of {len(df)} rows share content with at least one other row. Columns added: is_exact_duplicate, exact_dup_group_id."
    except Exception as e:
        return f"Error flagging duplicate rows: {str(e)}"


@tool_registry.register
def add_corruption_cols(ctx: RunContext[Any]) -> str:
    """Flag corrupt or zero-byte files in the current DataFrame with a per-row check.

    Adds `is_corrupt` (bool) and `corruption_reason` (str) columns so
    problem rows can be filtered/queried directly, checking for zero-byte
    files and unreadable/corrupt images (.jpg/.jpeg/.png/.bmp).
    """
    if ctx.deps.current_df is None:
        return "Error: No DataFrame loaded. Please run 'search_files' or 'create_dataset_dataframe' first."

    df = ctx.deps.current_df
    try:
        df = df.add_corruption_cols()
        ctx.deps.current_df = df
        corrupt_count = int(df.to_polars()["is_corrupt"].sum())
        return f"\u2705 Checked integrity: {corrupt_count} of {len(df)} rows are corrupt or zero-byte. Columns added: is_corrupt, corruption_reason."
    except Exception as e:
        return f"Error flagging corrupt rows: {str(e)}"


@tool_registry.register
def add_embedding_cols(ctx: RunContext[Any], max_chars: int = 4000, ignore_safety_limits: bool = False) -> str:
    """Add a semantic `embedding` column to the current DataFrame, computed from each file's content.

    Embeds text/code files (readme, source, config, etc.) using the same
    backend as filoma's RAG store (Ollama `nomic-embed-text` if reachable,
    else sentence-transformers `all-MiniLM-L6-v2`). Only the first
    `max_chars` characters of each file are embedded. Directories, binary
    files, and unreadable files get a null embedding (this includes images —
    for those, use `add_image_embedding_cols` instead). Follow up with
    `add_semantic_similarity_cols` to find each file's nearest neighbor by
    content.

    Embedding is CPU/model-bound (much slower than a hash or stat call per
    file), so a safety limit applies: if the DataFrame has more than
    ``_EMBED_SAFETY_LIMIT`` files that look embeddable, this refuses to run
    unless ``ignore_safety_limits=True``. On a whole-repo DataFrame this
    usually means build artifacts / vendored dependencies (`.venv`,
    `target/`, `node_modules`, `.git`) got swept in — narrow the DataFrame
    first with `filter_by_extension` / `filter_by_pattern`.

    Args:
        ctx: The run context.
        max_chars: Number of leading characters read from each file before
            embedding (default 4000, keeps large files fast).
        ignore_safety_limits: If True, embed regardless of how many files
            that implies. ONLY set to True if the user explicitly asked to
            embed everything / a large dataset.

    """
    if ctx.deps.current_df is None:
        return "Error: No DataFrame loaded. Please run 'search_files' or 'create_dataset_dataframe' first."

    df = ctx.deps.current_df
    try:
        if not ignore_safety_limits and "path" in df.columns:
            from filoma.core.rag import _is_text_file

            embeddable_count = sum(1 for p in df.to_polars()["path"].to_list() if _is_text_file(Path(p)))
            if embeddable_count > _EMBED_SAFETY_LIMIT:
                return (
                    f"\u26a0\ufe0f This DataFrame has {embeddable_count:,} files that look embeddable, which exceeds the "
                    f"safety limit of {_EMBED_SAFETY_LIMIT:,} (embedding is CPU/model-bound and can take a long time at this scale). "
                    "This often happens when the DataFrame covers an entire repo, including build artifacts or "
                    "vendored dependencies (.venv, target/, node_modules, .git), or a dataset where every image has a sidecar "
                    "text/XML/JSON annotation file. Narrow it first with filter_by_extension() / filter_by_pattern() (this tool "
                    "only counts/embeds text/code files, never images — if you want image embeddings, call "
                    "add_image_embedding_cols instead, which filters to images automatically), or re-run with "
                    "ignore_safety_limits=True to embed anyway."
                )

        df = df.add_embedding_cols(max_chars=max_chars)
        ctx.deps.current_df = df
        embedded_count = int(df.to_polars()["embedding"].is_not_null().sum())
        return f"\u2705 Embedded {embedded_count} of {len(df)} rows (non-text/unreadable files are skipped). Column added: embedding."
    except ImportError as e:
        return f"Error: RAG/embedding dependencies not available. Install with 'pip install filoma[rag]'. Details: {e}"
    except Exception as e:
        return f"Error computing embeddings: {str(e)}"


@tool_registry.register
def add_image_embedding_cols(ctx: RunContext[Any], model: str = "clip-vit-b32", device: Optional[str] = None, ignore_safety_limits: bool = False) -> str:
    """Add an `image_embedding` column to the current DataFrame, computed from each image's pixel content.

    Uses a CLIP vision encoder (via sentence-transformers, already a core
    filoma dependency — no extra install needed) to turn each image into a
    general-purpose visual-semantic feature vector (subject/scene/
    composition), not just a pixel or perceptual hash. Only files with a
    recognized image extension that Pillow can open are embedded;
    everything else (text, XML/JSON annotations, code, etc.) gets a null
    embedding automatically — no need to pre-filter the DataFrame to images
    yourself, and the safety limit below only ever counts actual image
    files, never the rest of the DataFrame. For text/code files, use
    `add_embedding_cols` instead. Follow up with
    `add_semantic_similarity_cols(embedding_col="image_embedding")` to build
    a visual similarity ranking / near-duplicate matrix.

    Model choices, fastest to slowest:
    - `clip-vit-b32` (default): fastest, 512-dim vectors. Good default for
      large batches or quick similarity checks.
    - `clip-vit-b16`: sharper features, ~3-4x slower than b32.
    - `clip-vit-l14`: largest and slowest, most accurate.

    A GPU is used automatically whenever one is available — by default
    (`device` unset), sentence-transformers auto-selects CUDA, then Apple
    Silicon MPS, then CPU. Pass `device` explicitly (e.g. `"cpu"`, `"cuda"`,
    `"cuda:1"`, `"mps"`) to override that choice; the device actually used
    is reported back in this tool's response.

    Image embedding is CPU/model-bound and decodes every image, so a safety
    limit applies: if the DataFrame has more than `_IMAGE_EMBED_SAFETY_LIMIT`
    image files, this refuses to run unless `ignore_safety_limits=True`.
    Narrow the DataFrame first with `filter_by_extension` / `filter_by_pattern`.

    Args:
        ctx: The run context.
        model: Which CLIP model to use (`clip-vit-b32`, `clip-vit-b16`, or
            `clip-vit-l14`), or any sentence-transformers image model id.
        device: Torch device to run on (`cpu`, `cuda`, `cuda:1`, `mps`, ...).
            If unset, the fastest available device is auto-selected.
        ignore_safety_limits: If True, embed regardless of how many image
            files that implies. ONLY set to True if the user explicitly
            asked to embed everything / a large dataset.

    """
    if ctx.deps.current_df is None:
        return "Error: No DataFrame loaded. Please run 'search_files' or 'create_dataset_dataframe' first."

    df = ctx.deps.current_df
    try:
        if not ignore_safety_limits and "path" in df.columns:
            from filoma.dedup import is_image_path

            embeddable_count = sum(1 for p in df.to_polars()["path"].to_list() if is_image_path(str(p)))
            if embeddable_count > _IMAGE_EMBED_SAFETY_LIMIT:
                return (
                    f"\u26a0\ufe0f This DataFrame has {embeddable_count:,} image files, which exceeds the safety limit of "
                    f"{_IMAGE_EMBED_SAFETY_LIMIT:,} (image embedding decodes and runs a vision model per file, which can take a "
                    "long time at this scale). Narrow it first with filter_by_extension() / filter_by_pattern(), or re-run with "
                    "ignore_safety_limits=True to embed anyway."
                )

        df = df.add_image_embedding_cols(model=model, device=device)
        ctx.deps.current_df = df
        embedded_count = int(df.to_polars()["image_embedding"].is_not_null().sum())
        used_device = df.lineage[-1]["parameters"].get("device") if df.lineage else None
        device_note = f" on {used_device}" if used_device else ""
        return f"\u2705 Embedded {embedded_count} of {len(df)} rows using '{model}'{device_note} (non-image/unreadable files are skipped). Column added: image_embedding."
    except ImportError as e:
        return f"Error: sentence-transformers not available. Install with 'pip install filoma[rag]'. Details: {e}"
    except ValueError as e:
        return f"Error: {str(e)}"
    except Exception as e:
        return f"Error computing image embeddings: {str(e)}"


@tool_registry.register
def add_metadata_embedding_cols(ctx: RunContext[Any], columns: Optional[List[str]] = None) -> str:
    """Add a `metadata_embedding` column derived from structured file metadata.

    Complements `add_embedding_cols` (which embeds file content) with a
    numeric feature vector built from the DataFrame's own columns: size,
    depth, extension, owner, group, is_dir, and timestamps. Pass this
    column to `add_semantic_similarity_cols` (via metadata_embedding_col)
    so similar-file rankings can reflect shared metadata (same extension,
    similar size, same owner) alongside shared meaning.

    Auto-selects from size_bytes/depth/suffix/owner/group/is_dir/
    modified_time/created_time \u2014 call add_file_stats_cols(),
    add_path_components(), and/or add_depth_col() first to make these
    columns available, or pass an explicit `columns` list.

    Args:
        ctx: The run context.
        columns: Optional explicit list of DataFrame columns to build the
            feature vector from. If omitted, auto-detects usable columns.

    """
    if ctx.deps.current_df is None:
        return "Error: No DataFrame loaded. Please run 'search_files' or 'create_dataset_dataframe' first."

    df = ctx.deps.current_df
    try:
        df = df.add_metadata_embedding_cols(columns=columns)
        ctx.deps.current_df = df
        return (
            f"\u2705 Built metadata embeddings for {len(df)} rows. Column added: metadata_embedding. "
            "Pass metadata_embedding_col='metadata_embedding' to add_semantic_similarity_cols to blend it with content similarity."
        )
    except ValueError as e:
        return f"Error: {str(e)}"
    except Exception as e:
        return f"Error computing metadata embeddings: {str(e)}"


@tool_registry.register
def add_semantic_similarity_cols(
    ctx: RunContext[Any],
    top_k: int = 1,
    embedding_col: str = "embedding",
    metadata_embedding_col: Optional[str] = None,
    content_weight: float = 0.6,
) -> str:
    """Add nearest-neighbor columns to the current DataFrame using cosine similarity of embeddings.

    Requires an embedding column to already exist \u2014 `add_embedding_cols`
    (text/code content, column `embedding`), `add_image_embedding_cols`
    (image content, column `image_embedding`), or
    `add_metadata_embedding_cols` (structured metadata, column
    `metadata_embedding`) alone if you want metadata-only similarity. Adds
    `nearest_neighbor_paths` and `nearest_neighbor_similarities` (list
    columns, most similar first) showing which other files are
    semantically related to each row \u2014 independent of folder or filename.
    Best suited to per-folder/per-dataset analysis (hundreds to low
    thousands of rows); this is an O(n^2) computation.

    Optionally blends in structured-metadata similarity on top of
    `embedding_col`: pass `metadata_embedding_col="metadata_embedding"`
    (after calling `add_metadata_embedding_cols` first) to weight
    `embedding_col` similarity against metadata similarity (extension,
    size, owner, timestamps) via `content_weight` (default 0.6 content /
    0.4 metadata).

    Args:
        ctx: The run context.
        top_k: Number of nearest neighbors to attach per row (default 1).
        embedding_col: Which embedding column to compute similarity over.
            Defaults to `embedding` (from `add_embedding_cols`); pass
            `image_embedding` (from `add_image_embedding_cols`) for visual
            similarity, or `metadata_embedding` (from
            `add_metadata_embedding_cols`) for metadata-only similarity when
            no content embedding is available.
        metadata_embedding_col: Optional column from
            `add_metadata_embedding_cols` to blend with `embedding_col`
            similarity. Leave unset if `embedding_col` is already
            `metadata_embedding` \u2014 blending a column with itself is a
            no-op.
        content_weight: Weight (0-1) given to `embedding_col` similarity when
            `metadata_embedding_col` is provided; ignored otherwise.

    """
    if ctx.deps.current_df is None:
        return "Error: No DataFrame loaded. Please run 'search_files' or 'create_dataset_dataframe' first."

    df = ctx.deps.current_df
    try:
        df = df.add_semantic_similarity_cols(embedding_col=embedding_col, top_k=top_k, metadata_embedding_col=metadata_embedding_col, content_weight=content_weight)
        ctx.deps.current_df = df
        matched_count = int(df.to_polars()["nearest_neighbor_paths"].is_not_null().sum())
        return (
            f"\u2705 Computed semantic similarity over '{embedding_col}': {matched_count} of {len(df)} rows matched to their nearest "
            "neighbor(s). Columns added: nearest_neighbor_paths, nearest_neighbor_similarities."
        )
    except ValueError as e:
        return f"Error: {str(e)}"
    except Exception as e:
        return f"Error computing semantic similarity: {str(e)}"


@tool_registry.register
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


@tool_registry.register
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


@tool_registry.register
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
        extension: File extension to filter by (e.g., 'py', 'jpg'). A leading dot is optional ('py' and '.py' both work). Do NOT use this for full filenames.
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


@tool_registry.register
def list_directory(ctx: RunContext[Any], path: str) -> str:
    """List files and folders in a directory (non-recursive, excludes hidden files).

    Use this for basic directory exploration. Shows folders first, then files.
    For hidden files (dotfiles), use list_directory_all instead.

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

        # Filter out hidden files (starting with .)
        items = [item for item in p.iterdir() if not item.name.startswith(".")]
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


@tool_registry.register
def list_directory_all(ctx: RunContext[Any], path: str) -> str:
    """List ALL files and folders in a directory including hidden files (dotfiles).

    Use this when you need to see hidden files like .gitignore, .env, .config files.
    Shows folders first, then files. Includes all items starting with '.'

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
        # Sort: directories first, then files, all case-insensitive
        items.sort(key=lambda x: (not x.is_dir(), x.name.lower()))

        report = f"CONTENTS OF: {p} (including hidden files)\n"
        report += f"{'-' * 50}\n"

        for item in items:
            # Mark hidden files with a special indicator
            is_hidden = item.name.startswith(".")
            prefix = "📁" if item.is_dir() else "📄"
            hidden_marker = " [hidden]" if is_hidden else ""

            # Special icons for known types (inspired by CLI)
            if not item.is_dir():
                suffix = item.suffix.lower()
                if suffix in [".png", ".jpg", ".jpeg", ".tif"]:
                    prefix = "🖼️"
                elif suffix in [".py", ".rs", ".js"]:
                    prefix = "💻"
                elif suffix in [".csv", ".json"]:
                    prefix = "📊"

            report += f"{prefix} {item.name}{'/' if item.is_dir() else ''}{hidden_marker}\n"

        return report

    except Exception as e:
        return f"Error listing directory: {str(e)}"


@tool_registry.register
def get_directory_tree(ctx: RunContext[Any], path: str) -> str:
    """Compatibility wrapper for listing immediate directory contents.

    Historically exposed as ``get_directory_tree`` in agent/MCP surfaces.
    Delegates to ``list_directory`` (non-recursive, hidden files excluded).
    """
    return list_directory(ctx=ctx, path=path)


@tool_registry.register
def list_available_tools(ctx: RunContext[Any]) -> str:
    """List all available tools and their capabilities.

    Use this if you are unsure of what operations are possible.
    """
    from filoma.filaraki.agent import FilarakiAgent

    return FilarakiAgent._build_api_reference()


@tool_registry.register
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

    return f"Error: Unknown operation '{operation}'. Supported: filter_by_extension, filter_by_pattern, sort_by_size, head, summary. Prefer using dedicated dataframe tools directly."


@tool_registry.register
def load_dataframe(ctx: RunContext[Any], path: str, format: Optional[str] = None) -> str:
    """Load a DataFrame from a file, e.g. one previously saved via `export_dataframe`, into the current session.

    The counterpart to `export_dataframe`. Use this to resume analysis on a
    DataFrame you already built and saved (with embeddings, similarity
    columns, corruption/duplicate flags, etc.) instead of recomputing
    everything from scratch — especially useful right after connecting (no
    DataFrame is loaded yet in a fresh session) or when picking up work
    saved by an earlier session, since an agent/MCP session's DataFrame
    only lives in that one connection's memory and doesn't survive a
    restart or reconnect.

    Args:
        ctx: The run context.
        path: Path to the file to load.
        format: `csv`, `json`, or `parquet`. If omitted, inferred from the
            file extension.

    """
    from filoma.dataframe import DataFrame

    try:
        df = DataFrame.load(path, format=format)
    except ValueError as e:
        return f"Error: {str(e)}"
    except Exception as e:
        return f"Error loading DataFrame: {str(e)}"

    ctx.deps.current_df = df
    return (
        f"\u2705 Loaded DataFrame from {path}: {len(df):,} rows, {len(df.columns)} columns.\n"
        f"\U0001f4cb Available columns: {', '.join(df.columns)}\n\n"
        "You can now use filter_by_extension(), add_semantic_similarity_cols(), summarize_dataframe(), etc. on it directly."
    )


@tool_registry.register
def export_dataframe(ctx: RunContext[Any], path: str, format: str = "csv") -> str:
    """Export the current DataFrame to a file.

    Pair with `load_dataframe` to resume this exact DataFrame (including
    any embedding/similarity/corruption columns already computed) in a
    later session without recomputing anything — parquet is the best
    format for this since it preserves list/nested columns (e.g.
    `embedding`, `nearest_neighbor_paths`) exactly, unlike CSV.

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


@tool_registry.register
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

        # In MCP stdio mode, never write file content directly to stdout.
        if _is_mcp_stdio_mode():
            content = p.read_text(encoding="utf-8", errors="replace")
            max_chars = 120_000
            truncated = len(content) > max_chars
            if truncated:
                content = content[:max_chars]

            ext = p.suffix.lstrip(".") or "text"
            out = f"FILE CONTENT ({p}):\n```{ext}\n{content}\n```"
            if truncated:
                out += "\n\nNote: Output truncated due to size. Use read_file with line ranges for deeper inspection."
            return out

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


@tool_registry.register
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


@tool_registry.register
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

        # Use cached probe_to_df to avoid re-scanning the same directory
        df = _cached_probe_to_df(ctx, str(p), enrich=enrich)

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


@tool_registry.register
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

        if _is_mcp_stdio_mode():
            mode = "ascii"

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

        if _is_mcp_stdio_mode():
            return f"{header}\n{final_preview}"

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


# ---------------------------------------------------------------------------
# RAG tools (Phase 5.1)
# ---------------------------------------------------------------------------


@tool_registry.register
def index_for_rag(ctx: RunContext[Any], path: str) -> str:
    """Index a directory of text files into a RAG vector store for semantic search.

    Walks the given directory, reads text/markdown/code files, chunks them
    into sentence-aware segments, embeds each chunk, and stores vectors in
    a local LanceDB database. Subsequent calls to ``search_rag`` will query
    against this index.

    The RAG store is cached on the agent session (``ctx.deps.rag_store``)
    so ``index_for_rag`` only needs to be called once per session.

    Args:
        ctx: The run context.
        path: Path to the directory containing text files to index.

    Returns:
        Summary message with the number of chunks indexed.

    """
    import tempfile

    p = Path(path).expanduser().resolve()
    if not p.exists():
        return f"Error: Path '{path}' does not exist."
    if not p.is_dir():
        return f"Error: '{path}' is not a directory."

    try:
        from filoma.core.rag import RagStore

        if not hasattr(ctx.deps, "rag_store") or ctx.deps.rag_store is None:
            db_dir = tempfile.mkdtemp(prefix="filoma_rag_")
            ctx.deps.rag_store = RagStore(db_path=db_dir)

        count = ctx.deps.rag_store.index(str(p))
        return f"Indexed {count} chunks from '{p}' into RAG store."
    except ImportError as e:
        return f"Error: RAG dependencies not available. Install with 'pip install filoma[rag]'. Details: {e}"


@tool_registry.register
def search_rag(ctx: RunContext[Any], query: str, top_k: int = 5) -> str:
    """Search the RAG vector store with a semantic query.

    Requires ``index_for_rag`` to have been called first in the session.
    Returns the top-k most relevant text chunks with their file paths
    and relevance scores.

    Args:
        ctx: The run context.
        query: Natural language query to search for.
        top_k: Number of results to return (default: 5, max: 20).

    Returns:
        Formatted text with search results including file paths,
        chunk text, and relevance distance.

    """
    if not hasattr(ctx.deps, "rag_store") or ctx.deps.rag_store is None:
        return "Error: No RAG store indexed. Call 'index_for_rag' first."

    top_k = min(max(top_k, 1), 20)
    results = ctx.deps.rag_store.search(query, top_k=top_k)

    if not results:
        return f"No results found for query: '{query}'"

    lines = [f"RAG search results for: '{query}' ({len(results)} results):"]
    for i, r in enumerate(results, 1):
        lines.append(f"\n--- Result {i} (distance={r['_distance']:.4f}) ---")
        lines.append(f"File: {r['path']}")
        lines.append(f"Chunk: {r['chunk_idx']}")
        lines.append(f"Text: {r['text'][:500]}{'...' if len(r['text']) > 500 else ''}")

    return "\n".join(lines)
