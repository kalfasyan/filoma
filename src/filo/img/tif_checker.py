from .base import BaseImageChecker

class TifChecker(BaseImageChecker):
    def check(self, path):
        # TODO: Implement TIF-specific checks
        return {"status": "not implemented"}
