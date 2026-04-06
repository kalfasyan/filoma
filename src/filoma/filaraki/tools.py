"""Tools for the FilarakiAgent."""

import html
import json
import os
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


def _is_mcp_stdio_mode() -> bool:
    """Return True when running under MCP stdio transport."""
    return os.getenv("FILOMA_MCP_STDIO", "0") == "1"


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

        # Derive total scanned files for accurate success-rate semantics
        total_files_checked = 0
        try:
            from filoma.directories import DirectoryProfiler, DirectoryProfilerConfig

            profiler = DirectoryProfiler(DirectoryProfilerConfig(build_dataframe=False))
            analysis = profiler.probe(str(p), max_depth=None)
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


def audit_dataset(
    ctx: RunContext[Any],
    path: str,
    mode: str = "concise",
    show_evidence: bool = False,
    export_path: Optional[str] = None,
    export_format: str = "json",
) -> str:
    """Run a full dataset audit workflow in one call.

    This orchestration tool executes three existing reports in sequence:
    - audit_corrupted_files
    - generate_hygiene_report
    - assess_migration_readiness

    It returns a concise or verbose summary and can optionally export a report.
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

    corruption_report = audit_corrupted_files(ctx, str(p))
    hygiene_report = generate_hygiene_report(ctx, str(p))
    readiness_report = assess_migration_readiness(ctx, str(p))

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
        df = filoma.probe_to_df(str(p), enrich=False)
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

    # Duplicate impact metrics from hygiene evidence
    duplicate_files_total = 0
    largest_duplicate_group_size = 0
    estimated_space_waste_bytes = 0
    try:
        dup_groups: list[list[str]] = []
        if hygiene_data:
            for issue in hygiene_data.get("issues", []):
                if issue.get("id") == "hygiene-duplicates":
                    evidence = issue.get("evidence", {})
                    dup_groups = evidence.get("duplicates", []) or []
                    break

        if dup_groups:
            duplicate_files_total = sum(len(group) for group in dup_groups if isinstance(group, list))
            largest_duplicate_group_size = max(len(group) for group in dup_groups if isinstance(group, list))

            # Estimate waste as size*(n-1) per group using first readable file as reference size
            for group in dup_groups:
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
    except Exception:
        duplicate_files_total = 0
        largest_duplicate_group_size = 0
        estimated_space_waste_bytes = 0

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
        "status": "ok"
        if profile_total_files in {0, total_files_checked}
        and readiness_total_files in {0, profile_total_files}
        else "warn",
    }

    # Extension shares for quick format composition signal.
    extension_share_pct = {
        ext: round((cnt / profile_total_files) * 100.0, 2)
        for ext, cnt in extension_counts.items()
        if profile_total_files > 0
    }

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
        next_actions.append({
            "priority": "high",
            "action": "Review and remove duplicate groups",
            "estimated_effort": f"{duplicate_groups} groups",
            "auto_followup_prompt": "Show all duplicate file paths and suggest deletions that preserve split integrity.",
        })
    if corrupted_files > 0 or zero_byte_files > 0:
        next_actions.append({
            "priority": "critical",
            "action": "Quarantine corrupted/zero-byte files",
            "estimated_effort": f"{corrupted_files + zero_byte_files} files",
            "auto_followup_prompt": "List corrupted and zero-byte files with exact paths.",
        })
    if reconciliation["status"] == "warn":
        next_actions.append({
            "priority": "medium",
            "action": "Investigate file-count mismatch across reports",
            "estimated_effort": "10-20 minutes",
            "auto_followup_prompt": "Explain why file totals differ across profile, integrity, and readiness checks.",
        })
    if not next_actions:
        next_actions.append({
            "priority": "low",
            "action": "Export and archive this audit baseline",
            "estimated_effort": "2 minutes",
            "auto_followup_prompt": "Export this report as markdown and summarize key baseline metrics.",
        })

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
            md.extend([
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
            ])
            out.write_text("\n".join(md), encoding="utf-8")
        else:
            # Self-contained HTML report for visual inspection and sharing.
            summary_rows = "".join(
                [
                    f"<tr><th>{html.escape(str(k))}</th><td>{html.escape(str(v))}</td></tr>"
                    for k, v in consolidated_report.get("summary", {}).items()
                ]
            )
            profile_rows = "".join(
                [
                    f"<tr><th>{html.escape(str(k))}</th><td>{html.escape(str(v))}</td></tr>"
                    for k, v in consolidated_report.get("dataset_profile", {}).items()
                ]
            )
            recon_rows = "".join(
                [
                    f"<tr><th>{html.escape(str(k))}</th><td>{html.escape(str(v))}</td></tr>"
                    for k, v in consolidated_report.get("reconciliation", {}).items()
                ]
            )
            timing_rows = "".join(
                [
                    f"<tr><th>{html.escape(str(k))}</th><td>{html.escape(str(v))}</td></tr>"
                    for k, v in consolidated_report.get("stage_timings", {}).items()
                ]
            )
            actions_rows = "".join(
                [
                    "<tr>"
                    f"<td>{html.escape(str(a.get('priority', '')))}</td>"
                    f"<td>{html.escape(str(a.get('action', '')))}</td>"
                    f"<td>{html.escape(str(a.get('estimated_effort', '')))}</td>"
                    f"<td>{html.escape(str(a.get('auto_followup_prompt', '')))}</td>"
                    "</tr>"
                    for a in consolidated_report.get("next_actions", [])
                ]
            )
            evidence_items = "".join(
                [f"<li>{html.escape(str(item))}</li>" for item in consolidated_report.get("evidence", [])]
            )

            version = consolidated_report.get("version", "unknown")

            html_doc = f"""<!doctype html>
<html lang=\"en\">
<head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>Filoma Dataset Audit Report</title>
    <style>
        :root {{
            --bg: #f6f8fb;
            --panel: #ffffff;
            --text: #1f2937;
            --muted: #6b7280;
            --accent: #0f766e;
            --border: #dbe3ee;
        }}
        body {{ margin: 0; padding: 24px; background: var(--bg); color: var(--text); font-family: 'Segoe UI', Tahoma, sans-serif; }}
        .wrap {{ max-width: 1100px; margin: 0 auto; }}
        .hero {{ background: linear-gradient(135deg, #ecfeff, #f0fdf4); border: 1px solid var(--border); border-radius: 14px; padding: 18px; }}
        h1 {{ margin: 0 0 8px; font-size: 1.5rem; }}
        .meta {{ color: var(--muted); font-size: 0.95rem; }}
        .grid {{ display: grid; gap: 14px; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); margin-top: 14px; }}
        .card {{ background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 12px; }}
        .card h2 {{ margin: 0 0 10px; font-size: 1.05rem; color: var(--accent); }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ border-bottom: 1px solid #eef2f7; text-align: left; padding: 7px 6px; vertical-align: top; font-size: 0.9rem; }}
        th {{ width: 45%; color: #0f172a; font-weight: 600; }}
        pre {{ white-space: pre-wrap; word-wrap: break-word; background: #0b1220; color: #e5e7eb; padding: 12px; border-radius: 10px; overflow: auto; }}
        ul {{ margin: 0; padding-left: 20px; }}
    </style>
</head>
<body>
    <div class=\"wrap\">
        <section class=\"hero\">
            <h1>Filoma Dataset Audit Report</h1>
            <div class=\"meta\">Target: {html.escape(str(p))} | Mode: {html.escape(mode)} | Version: {html.escape(str(version))}</div>
        </section>

        <section class=\"grid\">
            <article class=\"card\"><h2>Summary</h2><table>{summary_rows}</table></article>
            <article class=\"card\"><h2>Dataset Profile</h2><table>{profile_rows}</table></article>
            <article class=\"card\"><h2>Reconciliation</h2><table>{recon_rows}</table></article>
            <article class=\"card\"><h2>Stage Timings</h2><table>{timing_rows}</table></article>
            <article class=\"card\"><h2>Next Actions</h2><table><thead><tr><th>Priority</th><th>Action</th><th>Effort</th><th>Follow-up Prompt</th></tr></thead><tbody>{actions_rows}</tbody></table></article>
            <article class=\"card\"><h2>Evidence</h2><ul>{evidence_items or '<li>No evidence section requested.</li>'}</ul></article>
        </section>

        <section class=\"card\" style=\"margin-top:14px\">
            <h2>Full JSON Payload</h2>
            <pre>{html.escape(json.dumps(consolidated_report, indent=2, default=str))}</pre>
        </section>
    </div>
</body>
</html>
"""
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
        items = [item for item in p.iterdir() if not item.name.startswith('.')]
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
            is_hidden = item.name.startswith('.')
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


def get_directory_tree(ctx: RunContext[Any], path: str) -> str:
    """Compatibility wrapper for listing immediate directory contents.

    Historically exposed as ``get_directory_tree`` in agent/MCP surfaces.
    Delegates to ``list_directory`` (non-recursive, hidden files excluded).
    """
    return list_directory(ctx=ctx, path=path)


def list_available_tools(ctx: RunContext[Any]) -> str:
    """List all available tools and their capabilities.

    Use this if you are unsure of what operations are possible.
    """
    # Note: We import FilomaAgent here to avoid circular imports if necessary,
    # but since this is inside tools.py and FilomaAgent is in agent.py
    # which imports tools, we should be careful.
    # However, we can just hardcode or pass it.
    # For now, let's provide a clear manual list to be safe.
    from .agent import FilarakiAgent

    return FilarakiAgent.API_REFERENCE


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
