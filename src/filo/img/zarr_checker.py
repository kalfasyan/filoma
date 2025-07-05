from .base import BaseImageChecker

class ZarrChecker(BaseImageChecker):
    def check(self, path):
        # TODO: Implement Zarr-specific checks
        return {"status": "not implemented"}
