"""Structured response models for Filoma Brain orchestrator tools."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class AuditFinding(BaseModel):
    """Represents a single finding in an audit report."""

    id: str
    severity: str  # "critical", "high", "medium", "low", "info"
    category: str  # "integrity", "quality", "compliance", etc.
    description: str
    evidence: Dict[str, Any]
    confidence: float  # 0.0 to 1.0
    recommendation: str
    affected_paths: List[str]


class AuditReport(BaseModel):
    """Structured audit report with findings and metadata."""

    report_id: str
    timestamp: str
    target_path: str
    status: str  # "completed", "failed", "partial"
    summary: Dict[str, Any]
    findings: List[AuditFinding]
    execution_time_seconds: float
    tool_versions: Dict[str, str]


class HygieneMetric(BaseModel):
    """Single hygiene metric with value and threshold."""

    name: str
    value: float
    threshold: Optional[float]
    status: str  # "pass", "warn", "fail"
    description: str


class HygieneReport(BaseModel):
    """Comprehensive dataset hygiene report."""

    report_id: str
    timestamp: str
    target_path: str
    status: str
    overall_score: float  # 0.0 to 100.0
    metrics: List[HygieneMetric]
    issues: List[AuditFinding]
    recommendations: List[str]
    execution_time_seconds: float


class MigrationReadinessItem(BaseModel):
    """Single item in migration readiness assessment."""

    id: str
    category: str  # "data", "structure", "metadata", "compliance"
    status: str  # "ready", "warning", "blocked"
    description: str
    priority: str  # "high", "medium", "low"
    dependencies: List[str]
    estimated_effort_hours: Optional[float]


class MigrationReadinessReport(BaseModel):
    """Migration readiness assessment report."""

    report_id: str
    timestamp: str
    target_path: str
    status: str
    overall_readiness: float  # 0.0 to 100.0
    items: List[MigrationReadinessItem]
    blockers: List[str]
    risks: List[str]
    recommendations: List[str]
    estimated_migration_time_hours: Optional[float]
    execution_time_seconds: float
