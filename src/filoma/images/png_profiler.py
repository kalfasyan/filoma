from PIL import Image

from .base import BaseImageProfiler
from .image_profiler import ImageProfiler, ImageReport


class PngProfiler(BaseImageProfiler):
    def __init__(self):
        super().__init__()

    def probe(self, path) -> ImageReport:
        # Load PNG as numpy array
        img = Image.open(path)
        arr = __import__("numpy").array(img)
        profiler = ImageProfiler()
        report = profiler.probe(arr)
        # set file metadata
        report.file_type = "png"
        report.path = str(path)
        return report
