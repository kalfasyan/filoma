"""Zarr image profiler implementation (placeholder)."""

from .base import BaseImageProfiler
from .image_profiler import ImageReport


class ZarrProfiler(BaseImageProfiler):
    """Profiler for Zarr containers (currently placeholder)."""

    def __init__(self):
        """Initialize the Zarr profiler."""
        super().__init__()

    def probe(self, path) -> ImageReport:
        """Probe the Zarr store at `path` and return an ImageReport.

        Currently returns a placeholder report with status set to
        "not implemented".
        """
        return ImageReport(path=str(path), status="not implemented")
