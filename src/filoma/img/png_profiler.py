import numpy as np
from PIL import Image

from .base import BaseImageProfiler
from .image_profiler import ImageProfiler


class PngProfiler(BaseImageProfiler):
    def __init__(self):
        super().__init__()

    def analyze(self, path):
        # Load PNG as numpy array
        img = Image.open(path)
        arr = np.array(img)
        analyzer = ImageProfiler()
        report = analyzer.analyze(arr)
        report["file_type"] = "png"
        report["path"] = str(path)
        return report
