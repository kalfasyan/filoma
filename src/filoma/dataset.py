"""High-level Dataset management entity for filoma."""

import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Union

from .core.snapshot import DatasetSnapshot, snapshot
from .core.snapshot import verify as _verify_snapshot
from .core.verifier import DatasetVerifier
from .dataframe import DataFrame


class Dataset:
    """A high-level entity for managing datasets.

    Supports a fluent chain — ``Dataset(p).scan().enrich().verify().report()`` —
    or traditional method-by-method calls. Fluent verbs cache their result
    on the instance and return ``self``; the cached result is exposed via the
    matching read-only property (:attr:`dataframe`, :attr:`verification`,
    :attr:`quality`, :attr:`duplicates`, :attr:`report_path`).
    """

    def __init__(self, root_path: Union[str, Path]):
        """Initialize the Dataset with a root path."""
        self.root_path = Path(root_path).resolve()
        if not self.root_path.exists():
            raise FileNotFoundError(f"Path does not exist: {self.root_path}")
        self.snapshot: Optional[DatasetSnapshot] = None
        self._df: Optional[DataFrame] = None
        self._cached_probe_result: Any = None
        self._verification: Optional[Dict[str, Any]] = None
        self._quality: Optional[DatasetVerifier] = None
        self._duplicates: Optional[Dict[str, Any]] = None
        self._report_path: Optional[Path] = None

    # --- Fluent chain verbs -------------------------------------------------

    def scan(self, mode: str = "fast", **kwargs) -> "Dataset":
        """Create an integrity snapshot of the dataset.

        Alias of :meth:`snap` kept for the fluent ``scan().enrich().verify()``
        chain. Returns ``self``.
        """
        return self.snap(mode=mode, **kwargs)

    def enrich(self, **kwargs) -> "Dataset":
        """Materialize the enriched DataFrame and cache it. Returns ``self``.

        After this call the DataFrame is available via :attr:`dataframe`. Use
        :meth:`to_dataframe` if you want the DataFrame returned directly.
        """
        if self._df is None:
            from . import probe_to_df

            self._df = probe_to_df(str(self.root_path), **kwargs)
        return self

    def report(
        self,
        path: Optional[Union[str, Path]] = None,
        format: str = "html",
        mode: str = "concise",
        show_evidence: bool = True,
    ) -> "Dataset":
        """Generate an audit report and remember its location.

        Wraps :func:`filoma.filaraki.tools.audit_dataset`. If ``path`` is
        ``None``, writes to ``<tempdir>/<root>_audit.<ext>``. Returns ``self``;
        the resolved destination is available via :attr:`report_path`.
        """
        from .filaraki.tools import audit_dataset

        fmt = (format or "html").lower()
        if path is None:
            ext = {"html": "html", "md": "md", "json": "json"}.get(fmt, fmt)
            dest = Path(tempfile.gettempdir()) / f"{self.root_path.name}_audit.{ext}"
        else:
            dest = Path(path)

        # audit_dataset is a pydantic-ai tool: the RunContext is unused when
        # we only care about the export side-effect.
        audit_dataset(
            None,  # type: ignore[arg-type]
            str(self.root_path),
            mode=mode,
            show_evidence=show_evidence,
            export_path=str(dest),
            export_format=fmt,
        )
        self._report_path = dest
        return self

    # --- Existing API (back-compat) -----------------------------------------

    def snap(self, mode: str = "fast", **kwargs) -> "Dataset":
        """Perform a scan and create a snapshot."""
        self.snapshot = snapshot(str(self.root_path), mode=mode, **kwargs)
        return self

    def probe(self, **kwargs) -> Any:
        """Perform a directory profile."""
        if self._cached_probe_result is None:
            from . import probe

            self._cached_probe_result = probe(str(self.root_path), **kwargs)
        return self._cached_probe_result

    def to_dataframe(self, **kwargs) -> "DataFrame":
        """Convert the dataset scan into a polars DataFrame."""
        if self._df is None:
            from . import probe_to_df

            self._df = probe_to_df(str(self.root_path), **kwargs)
        return self._df

    def verify(
        self,
        snapshot_path: Optional[Union[str, Path]] = None,
        **kwargs,
    ) -> "Dataset":
        """Verify dataset integrity against a snapshot.

        If ``snapshot_path`` is given, verifies against that JSON file.
        Otherwise uses the in-memory snapshot (auto-creating it via
        :meth:`scan` if absent). The verification result dict is stored on
        :attr:`verification`.

        Returns ``self`` for chaining. (Earlier versions returned the dict
        directly; access it via ``ds.verify(...).verification`` instead.)
        """
        if snapshot_path is not None:
            self._verification = _verify_snapshot(
                str(snapshot_path),
                target_path=str(self.root_path),
                **kwargs,
            )
            return self

        if self.snapshot is None:
            self.scan()

        # In-memory snapshot: hand the object directly to the underlying
        # verifier (no JSON roundtrip).
        assert self.snapshot is not None
        self._verification = _verify_snapshot(
            self.snapshot,
            target_path=str(self.root_path),
            **kwargs,
        )
        return self

    def run_quality_scan(self) -> Any:
        """Run deep data quality analysis."""
        verifier = DatasetVerifier(str(self.root_path))
        verifier.run_all()
        self._quality = verifier
        return verifier

    def dedup(self, **kwargs) -> Any:
        """Perform deduplication."""
        from .dedup import find_duplicates

        paths = [os.path.join(root, fname) for root, _, files in os.walk(str(self.root_path)) for fname in files]
        result = find_duplicates(paths, **kwargs)
        self._duplicates = result
        return result

    def get_filaraki(self) -> Any:
        """Access the Filaraki agentic AI tool for this dataset.

        Returns a FilarakiAgent instance configured with this dataset's root path
        as the default working directory, so all agent tool calls operate on the dataset.
        """
        from .filaraki import get_agent

        return get_agent(working_dir=str(self.root_path))

    def get_brain(self) -> Any:
        """Access the agentic AI tool for this dataset.

        .. deprecated::
            Use :meth:`get_filaraki` instead.
        """
        return self.get_filaraki()

    def invalidate_cache(self) -> None:
        """Clear all cached internal states."""
        self._df = None
        self._cached_probe_result = None
        self._verification = None
        self._quality = None
        self._duplicates = None
        self._report_path = None

    # --- Read-only views over cached results --------------------------------

    @property
    def dataframe(self) -> Optional["DataFrame"]:
        """Cached enriched DataFrame, or ``None`` if :meth:`enrich` not called."""
        return self._df

    @property
    def verification(self) -> Optional[Dict[str, Any]]:
        """Cached integrity-verification result, or ``None``."""
        return self._verification

    @property
    def quality(self) -> Optional[DatasetVerifier]:
        """Cached quality-scan result, or ``None``."""
        return self._quality

    @property
    def duplicates(self) -> Optional[Dict[str, Any]]:
        """Cached duplicate-scan result, or ``None``."""
        return self._duplicates

    @property
    def report_path(self) -> Optional[Path]:
        """Path to the most recent report written by :meth:`report`."""
        return self._report_path
