from .base import BaseImageProfiler
from .image_profiler import ImageReport


class TifProfiler(BaseImageProfiler):
    def __init__(self):
        super().__init__()

    def probe(self, path) -> ImageReport:
        # TODO: Implement TIF-specific analysis
        return ImageReport(path=str(path), status="not implemented")
