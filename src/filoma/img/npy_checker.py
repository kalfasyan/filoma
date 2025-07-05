from .base import BaseImageChecker


class NpyChecker(BaseImageChecker):
    def check(self, path):
        # TODO: Implement NPY-specific checks
        return {"status": "not implemented"}
