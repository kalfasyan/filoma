"""Profiler for NumPy `.npy` files.

Currently a placeholder that returns a not-implemented status.
"""

from .base import BaseImageProfiler
from .image_profiler import ImageReport


class NpyProfiler(BaseImageProfiler):
    """Profiler for `.npy` files (placeholder implementation)."""

    def __init__(self):
        """Initialize the NpyProfiler."""
        super().__init__()

    def probe(self, path) -> ImageReport:
        """Probe the `.npy` file at `path` and return an ImageReport.

        Currently returns a placeholder report with status set to
        "not implemented".
        """
        return ImageReport(path=str(path), status="not implemented")
