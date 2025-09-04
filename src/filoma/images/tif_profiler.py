from .base import BaseImageProfiler


class TifProfiler(BaseImageProfiler):
    def __init__(self):
        super().__init__()

    def probe(self, path):
        # TODO: Implement TIF-specific analysis
        return {"status": "not implemented", "path": str(path)}
