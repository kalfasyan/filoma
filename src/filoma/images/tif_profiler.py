"""TIFF image profiler implementation (placeholder)."""

from .base import BaseImageProfiler
from .image_profiler import ImageReport


class TifProfiler(BaseImageProfiler):
    """Profiler for TIFF files (currently placeholder)."""

    def __init__(self):
        """Initialize the TIFF profiler."""
        super().__init__()

    def probe(self, path) -> ImageReport:
        """Probe the TIFF at `path` and return an ImageReport.

        Currently returns a placeholder report with status set to
        "not implemented".
        """
        return ImageReport(path=str(path), status="not implemented")
