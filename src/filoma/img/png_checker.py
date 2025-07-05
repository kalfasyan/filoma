import numpy as np
from PIL import Image

from .base import BaseImageChecker
from .image_analyzer import ImageAnalyzer


class PngChecker(BaseImageChecker):
    def check(self, path):
        # Load PNG as numpy array
        img = Image.open(path)
        arr = np.array(img)
        analyzer = ImageAnalyzer()
        report = analyzer.analyze(arr)
        report["file_type"] = "png"
        report["path"] = str(path)
        return report
