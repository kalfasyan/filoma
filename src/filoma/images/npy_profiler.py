from .base import BaseImageProfiler


class NpyProfiler(BaseImageProfiler):
    def __init__(self):
        super().__init__()

    def probe(self, path):
        # TODO: Implement NPY-specific analysis
        return {"status": "not implemented", "path": str(path)}
