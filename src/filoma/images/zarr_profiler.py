from .base import BaseImageProfiler
from .image_profiler import ImageReport


class ZarrProfiler(BaseImageProfiler):
    def __init__(self):
        super().__init__()

    def probe(self, path) -> ImageReport:
        # TODO: Implement Zarr-specific analysis
        return ImageReport(path=str(path), status="not implemented")
