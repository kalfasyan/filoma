"""PNG image profiler implementation."""

from PIL import Image

from .base import BaseImageProfiler
from .image_profiler import ImageProfiler, ImageReport


class PngProfiler(BaseImageProfiler):
    """Profiler that analyzes PNG image files using Pillow."""

    def __init__(self):
        """Initialize the PNG profiler."""
        super().__init__()

    def probe(self, path) -> ImageReport:
        """Open the PNG at `path`, convert to a NumPy array, and analyze it.

        Returns an :class:`ImageReport` populated with basic statistics.
        """
        # Load PNG as numpy array
        img = Image.open(path)
        arr = __import__("numpy").array(img)
        profiler = ImageProfiler()
        report = profiler.probe(arr)
        # set file metadata
        report.file_type = "png"
        report.path = str(path)
        return report
