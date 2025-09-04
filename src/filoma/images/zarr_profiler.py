from .base import BaseImageProfiler


class ZarrProfiler(BaseImageProfiler):
    def __init__(self):
        super().__init__()

    def probe(self, path):
        # TODO: Implement Zarr-specific analysis
        return {"status": "not implemented", "path": str(path)}
