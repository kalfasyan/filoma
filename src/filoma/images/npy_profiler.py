from .base import BaseImageProfiler
from .image_profiler import ImageReport


class NpyProfiler(BaseImageProfiler):
    def __init__(self):
        super().__init__()

    def probe(self, path) -> ImageReport:
        # TODO: Implement NPY-specific analysis
        return ImageReport(path=str(path), status="not implemented")
