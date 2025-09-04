import numpy as np
from PIL import Image

from .base import BaseImageProfiler
from .image_profiler import ImageProfiler


class PngProfiler(BaseImageProfiler):
    def __init__(self):
        super().__init__()

    def probe(self, path):
        # Load PNG as numpy array
        img = Image.open(path)
        arr = np.array(img)
        profiler = ImageProfiler()
        report = profiler.probe(arr)
        report["file_type"] = "png"
        report["path"] = str(path)
        return report
