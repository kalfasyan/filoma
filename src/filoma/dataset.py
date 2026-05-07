"""High-level Dataset management entity for filoma."""

from pathlib import Path
from typing import Any, Dict, Optional, Union

from .core.snapshot import DatasetSnapshot, snapshot, verify
from .core.verifier import DatasetVerifier
from .dataframe import DataFrame


class Dataset:
    """A high-level entity for managing datasets."""

    def __init__(self, root_path: Union[str, Path]):
        """Initialize the Dataset with a root path."""
        self.root_path = Path(root_path).resolve()
        if not self.root_path.exists():
            raise FileNotFoundError(f"Path does not exist: {self.root_path}")
        self.snapshot: Optional[DatasetSnapshot] = None
        self._df: Optional[DataFrame] = None
        self._cached_probe_result: Any = None

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

    def verify(self, snapshot_path: Optional[Union[str, Path]] = None, **kwargs) -> Dict[str, Any]:
        """Perform integrity verification."""
        path = snapshot_path or (self.snapshot.root_path if self.snapshot else None)
        if not path:
            raise ValueError("No snapshot provided or exists.")
        return verify(str(path), target_path=str(self.root_path), **kwargs)

    def run_quality_scan(self) -> Any:
        """Run deep data quality analysis."""
        verifier = DatasetVerifier(str(self.root_path))
        verifier.run_all()
        return verifier

    def dedup(self, **kwargs) -> Any:
        """Perform deduplication."""
        import os

        from .dedup import find_duplicates

        paths = [os.path.join(root, fname) for root, _, files in os.walk(str(self.root_path)) for fname in files]
        return find_duplicates(paths, **kwargs)

    def get_brain(self) -> Any:
        """Access the agentic AI tool for this dataset."""
        from .brain.agent import get_agent

        return get_agent()

    def invalidate_cache(self) -> None:
        """Clear all cached internal states."""
        self._df = None
        self._cached_probe_result = None
