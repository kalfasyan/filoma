"""High-level Dataset management entity for filoma.

Dataset is a backward-compatible subclass of Pipeline that preserves
the legacy API (``snap``, ``probe``, ``to_dataframe``, etc.) while
benefiting from the stage-based shared-state architecture underneath.
"""

from pathlib import Path
from typing import Any, Optional, Union

from .pipeline import Pipeline


class Dataset(Pipeline):
    """A high-level entity for managing datasets.

    Supports the fluent chain ``Dataset(p).scan().enrich().verify().report()``
    inherited from :class:`Pipeline`, plus backward-compatible legacy methods
    (``snap``, ``probe``, ``to_dataframe``, ``run_quality_scan``,
    ``get_filaraki``).

    The underlying stage-based pipeline shares state across stages so the
    full chain walks the filesystem only once.
    """

    def __init__(self, root_path: Union[str, Path]) -> None:
        """Initialize with a dataset root path; delegates to :class:`Pipeline`."""
        super().__init__(root_path)
        self._cached_probe_result: Any = None

    def snap(self, mode: str = "fast", **kwargs: Any) -> "Dataset":
        """Perform a scan and create a snapshot (legacy alias for ``scan``)."""
        return self.scan(mode=mode, **kwargs)  # type: ignore[return-value]

    def probe(self, **kwargs: Any) -> Any:
        """Perform a directory profile (cached)."""
        if self._cached_probe_result is None:
            import filoma

            self._cached_probe_result = filoma.probe(str(self.root_path), **kwargs)
        return self._cached_probe_result

    def to_dataframe(self, **kwargs: Any) -> Any:
        """Convert the dataset scan into a polars DataFrame."""
        if self._state.dataframe is None:
            self.enrich(**kwargs)
        return self._state.dataframe

    def verify(  # type: ignore[override]
        self,
        snapshot_path: Optional[Union[str, Path]] = None,
        **kwargs: Any,
    ) -> "Dataset":
        """Verify dataset integrity against a snapshot. Returns self for chaining."""
        super().verify(snapshot_path=snapshot_path, **kwargs)
        return self

    def run_quality_scan(self) -> Any:
        """Run deep data quality analysis."""
        from .core.verifier import DatasetVerifier

        verifier = DatasetVerifier(str(self.root_path))
        verifier.run_all()
        self._state.quality = verifier
        return verifier

    def dedup(self, **kwargs: Any) -> Any:
        """Find duplicate files. Returns the dedup result dict."""
        super().dedup(**kwargs)
        return self._state.duplicates

    def get_filaraki(self) -> Any:
        """Access the Filaraki agentic AI tool for this dataset."""
        from .filaraki import get_agent

        return get_agent(working_dir=str(self.root_path))

    def get_brain(self) -> Any:
        """Access the agentic AI tool for this dataset (deprecated, use ``get_filaraki``)."""
        return self.get_filaraki()

    def invalidate_cache(self) -> None:
        """Clear all cached internal states."""
        super().invalidate_cache()
        self._cached_probe_result = None
