"""Quality gate policy checking for filoma audit.

Reads a ``filoma-gates.yml`` policy file and compares its thresholds
against the structured output of ``audit_dataset``.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from loguru import logger


@dataclass
class GateResult:
    """Outcome of a single quality gate check."""

    name: str
    threshold: float
    actual: float
    passed: bool


@dataclass
class GatePolicy:
    """Parsed quality gate policy from a YAML file."""

    version: int = 1
    gates: Dict[str, float] = field(default_factory=dict)


# Maps gate names to their path inside the consolidated audit report.
# Path is a list of keys to drill into.
_GATE_PATH_MAP: Dict[str, List[str]] = {
    "duplicate_ratio_pct": ["summary", "duplicate_ratio_pct"],
    "corrupted_files": ["summary", "corrupted_files"],
    "zero_byte_files": ["summary", "zero_byte_files"],
    "hygiene_score": ["summary", "hygiene_score"],
    "migration_readiness": ["summary", "migration_readiness"],
    "migration_blockers": ["summary", "migration_blockers"],
}

# Gate names that compare "less than or equal" (fewer is better).
# All others compare "greater than or equal" (higher is better).
_LOWER_IS_BETTER: set[str] = {
    "duplicate_ratio_pct",
    "corrupted_files",
    "zero_byte_files",
    "migration_blockers",
}


def _load_policy(policy_path: Union[str, Path]) -> Optional[GatePolicy]:
    """Load and parse a gate policy YAML file.

    Returns ``None`` if the file is missing or invalid, with appropriate
    log warnings.
    """
    policy_path = Path(policy_path).expanduser().resolve()
    if not policy_path.exists():
        logger.warning(f"Gate policy file not found: {policy_path}")
        return None

    try:
        import yaml
    except ImportError:
        logger.warning("pyyaml is not installed — gate checking skipped.")
        return None

    try:
        raw = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error(f"Failed to parse gate policy YAML: {e}")
        return None

    if not isinstance(raw, dict):
        logger.error("Gate policy YAML must be a dictionary with a 'gates' key.")
        return None

    version = raw.get("version", 1)
    gates_raw = raw.get("gates", {})
    gates: Dict[str, float] = {}

    for name, value in gates_raw.items():
        if not isinstance(name, str):
            continue
        try:
            gates[name] = float(value)
        except (TypeError, ValueError):
            logger.warning(f"Gate '{name}' has non-numeric threshold '{value}' — skipping.")

    return GatePolicy(version=int(version), gates=gates)


def _get_nested(data: dict, path: List[str]) -> Optional[float]:
    """Drill into a nested dict by *path* and return a float, or None."""
    current: Any = data
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
        if current is None:
            return None
    try:
        return float(current)
    except (TypeError, ValueError):
        return None


def _get_class_min_samples(data: dict) -> Optional[float]:
    """Extract the minimum class sample count from the hygiene sub-report.

    The hygiene report carries class distribution under
    ``reports.hygiene.issues[*].evidence.class_distribution``.
    Returns the smallest per-class count, or None.
    """
    reports = data.get("reports", {})
    hygiene = reports.get("hygiene", {})
    if not isinstance(hygiene, dict):
        return None

    issues = hygiene.get("issues", [])
    if not isinstance(issues, list):
        return None

    for issue in issues:
        if not isinstance(issue, dict):
            continue
        evidence = issue.get("evidence", {})
        if not isinstance(evidence, dict):
            continue
        class_dist = evidence.get("class_distribution", {})
        if isinstance(class_dist, dict) and class_dist:
            values = [v for v in class_dist.values() if isinstance(v, (int, float))]
            if values:
                return float(min(values))

    return None


def check_gates(
    policy_path: Union[str, Path],
    audit_data: dict,
) -> List[GateResult]:
    """Load a gate policy and check all gates against *audit_data*.

    Returns a list of :class:`GateResult` — one per gate defined in the
    policy. Unknown gate names are skipped with a warning. Missing data
    for a gate also results in a warning (not a failure).

    Args:
        policy_path: Path to a ``filoma-gates.yml`` file.
        audit_data: The ``consolidated_report`` dict from ``audit_dataset``.

    """
    policy = _load_policy(policy_path)
    results: List[GateResult] = []

    if policy is None:
        return results

    for name, threshold in policy.gates.items():
        if name not in _GATE_PATH_MAP and name != "class_min_samples":
            logger.warning(f"Unknown gate '{name}' in policy — skipping.")
            continue

        if name == "class_min_samples":
            actual = _get_class_min_samples(audit_data)
            if actual is None:
                logger.warning("Gate 'class_min_samples' could not extract class distribution from audit data — skipping.")
                continue
        else:
            actual = _get_nested(audit_data, _GATE_PATH_MAP[name])
            if actual is None:
                logger.warning(f"Gate '{name}' could not find data at path {_GATE_PATH_MAP[name]} — skipping.")
                continue

        if name in _LOWER_IS_BETTER:
            passed = actual <= threshold
        else:
            passed = actual >= threshold

        results.append(GateResult(name=name, threshold=threshold, actual=actual, passed=passed))

    return results
