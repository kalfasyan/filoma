"""Stage-based Pipeline for dataset profiling with shared state.

Replaces the monolithic Dataset class with composable pipeline stages
that share a PipelineState, eliminating redundant filesystem walks.
"""

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Protocol, Union

from .core.snapshot import DatasetSnapshot, snapshot
from .core.snapshot import verify as _verify_snapshot
from .core.verifier import DatasetVerifier


@dataclass
class PipelineState:
    """Shared state passed between pipeline stages.

    Each stage reads from and writes to this object, avoiding redundant
    filesystem walks that the old monolithic Dataset class performed
    (up to ~5 walks for a full scan-enrich-verify-dedup-report chain).
    """

    root_path: Path
    snapshot: Optional[DatasetSnapshot] = None
    dataframe: Optional[Any] = None
    verification: Optional[Dict[str, Any]] = None
    quality: Optional[DatasetVerifier] = None
    duplicates: Optional[Dict[str, Any]] = None
    report_path: Optional[Path] = None


class Stage(Protocol):
    """Single-purpose pipeline stage."""

    def run(self, state: PipelineState) -> PipelineState:
        """Execute this stage against *state* and return the mutated state."""
        ...


class ScanStage:
    """Create an integrity snapshot of the dataset."""

    def __init__(self, mode: str = "fast", **kwargs: Any) -> None:
        """Initialize with snapshot mode and extra options."""
        self._mode = mode
        self._kwargs = kwargs

    def run(self, state: PipelineState) -> PipelineState:
        """Snapshot the dataset root and store the result on *state*."""
        state.snapshot = snapshot(str(state.root_path), mode=self._mode, **self._kwargs)
        return state


class EnrichStage:
    """Materialize an enriched DataFrame from the dataset root."""

    def __init__(self, **kwargs: Any) -> None:
        """Initialize with options forwarded to ``probe_to_df``."""
        self._kwargs = kwargs

    def run(self, state: PipelineState) -> PipelineState:
        """Build an enriched DataFrame and store it on *state*."""
        from filoma import probe_to_df

        state.dataframe = probe_to_df(str(state.root_path), **self._kwargs)
        return state


class VerifyStage:
    """Verify dataset integrity against an in-memory or on-disk snapshot."""

    def __init__(self, snapshot_path: Optional[Union[str, Path]] = None, **kwargs: Any) -> None:
        """Initialize with optional snapshot path and verification options."""
        self._snapshot_path = snapshot_path
        self._kwargs = kwargs

    def run(self, state: PipelineState) -> PipelineState:
        """Verify dataset integrity and store the result dict on *state*."""
        if self._snapshot_path is not None:
            state.verification = _verify_snapshot(
                str(self._snapshot_path),
                target_path=str(state.root_path),
                **self._kwargs,
            )
            return state

        if state.snapshot is None:
            state = ScanStage().run(state)

        assert state.snapshot is not None
        state.verification = _verify_snapshot(
            state.snapshot,
            target_path=str(state.root_path),
            **self._kwargs,
        )
        return state


class DedupStage:
    """Find duplicate files using cached dataframe paths when available."""

    def __init__(self, **kwargs: Any) -> None:
        """Initialize with options forwarded to ``find_duplicates``."""
        self._kwargs = kwargs

    def run(self, state: PipelineState) -> PipelineState:
        """Scan for duplicates and store grouped results on *state*.

        Prefers paths from a cached dataframe (no re-walk); falls back
        to ``os.walk`` when no dataframe has been built yet.
        """
        from .dedup import find_duplicates

        if state.dataframe is not None:
            paths = state.dataframe.df["path"].to_list()
        else:
            paths = [os.path.join(root, fname) for root, _, files in os.walk(str(state.root_path)) for fname in files]
        state.duplicates = find_duplicates(paths, **self._kwargs)
        return state


class ReportStage:
    """Generate an audit report using cached dataframe to avoid re-walking."""

    def __init__(
        self,
        path: Optional[Union[str, Path]] = None,
        format: str = "html",
        mode: str = "concise",
        show_evidence: bool = True,
    ) -> None:
        """Initialize with report destination, format, and verbosity."""
        self._path = path
        self._format = format
        self._mode = mode
        self._show_evidence = show_evidence

    def run(self, state: PipelineState) -> PipelineState:
        """Run the three-stage audit and write the export, reusing cached dataframe."""
        from .filaraki.tools import audit_dataset

        fmt = (self._format or "html").lower()
        if self._path is None:
            ext = {"html": "html", "md": "md", "json": "json"}.get(fmt, fmt)
            dest = Path(tempfile.gettempdir()) / f"{state.root_path.name}_audit.{ext}"
        else:
            dest = Path(self._path)

        audit_dataset(
            None,  # type: ignore[arg-type]
            str(state.root_path),
            mode=self._mode,
            show_evidence=self._show_evidence,
            export_path=str(dest),
            export_format=fmt,
            dataframe=state.dataframe,
        )
        state.report_path = dest
        return state


class Pipeline:
    """Stage-based pipeline for dataset profiling.

    Provides a fluent chain API (``scan().enrich().verify().dedup().report()``)
    with shared state to avoid redundant filesystem walks.

    ``Dataset`` is a backward-compatible subclass of ``Pipeline`` that adds
    the legacy methods (``snap``, ``probe``, ``to_dataframe``, etc.).
    """

    def __init__(self, root_path: Union[str, Path]):
        """Initialize with a dataset root path; raises ``FileNotFoundError`` if missing."""
        self._state = PipelineState(root_path=Path(root_path).resolve())
        if not self._state.root_path.exists():
            raise FileNotFoundError(f"Path does not exist: {self._state.root_path}")

    # -- Fluent chain verbs -------------------------------------------------

    def scan(self, mode: str = "fast", **kwargs: Any) -> "Pipeline":
        """Create an integrity snapshot of the dataset. Returns ``self``."""
        ScanStage(mode=mode, **kwargs).run(self._state)
        return self

    def enrich(self, **kwargs: Any) -> "Pipeline":
        """Materialize an enriched DataFrame. Returns ``self``."""
        EnrichStage(**kwargs).run(self._state)
        return self

    def verify(
        self,
        snapshot_path: Optional[Union[str, Path]] = None,
        **kwargs: Any,
    ) -> "Pipeline":
        """Verify integrity against a snapshot. Returns ``self``."""
        VerifyStage(snapshot_path=snapshot_path, **kwargs).run(self._state)
        return self

    def dedup(self, **kwargs: Any) -> "Pipeline":
        """Find duplicate files. Returns ``self``."""
        DedupStage(**kwargs).run(self._state)
        return self

    def report(
        self,
        path: Optional[Union[str, Path]] = None,
        format: str = "html",
        mode: str = "concise",
        show_evidence: bool = True,
    ) -> "Pipeline":
        """Generate an audit report. Returns ``self``."""
        ReportStage(
            path=path,
            format=format,
            mode=mode,
            show_evidence=show_evidence,
        ).run(self._state)
        return self

    def invalidate_cache(self) -> None:
        """Clear all cached internal states."""
        self._state.snapshot = None
        self._state.dataframe = None
        self._state.verification = None
        self._state.quality = None
        self._state.duplicates = None
        self._state.report_path = None

    # -- Read-only views over cached results --------------------------------

    @property
    def root_path(self) -> Path:
        """Resolved root path of the dataset."""
        return self._state.root_path

    @property
    def snapshot(self) -> Optional[DatasetSnapshot]:
        """Cached integrity snapshot, or ``None`` if :meth:`scan` not called."""
        return self._state.snapshot

    @property
    def dataframe(self) -> Optional[Any]:
        """Cached enriched DataFrame, or ``None`` if :meth:`enrich` not called."""
        return self._state.dataframe

    @property
    def verification(self) -> Optional[Dict[str, Any]]:
        """Cached integrity-verification result, or ``None``."""
        return self._state.verification

    @property
    def quality(self) -> Optional[DatasetVerifier]:
        """Cached quality-scan result, or ``None``."""
        return self._state.quality

    @property
    def duplicates(self) -> Optional[Dict[str, Any]]:
        """Cached duplicate-scan result, or ``None``."""
        return self._state.duplicates

    @property
    def report_path(self) -> Optional[Path]:
        """Path to the most recent report written by :meth:`report`."""
        return self._state.report_path
