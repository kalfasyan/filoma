import numpy as np
from PIL import Image

from filoma.images.png_profiler import PngProfiler


def test_png_checker(tmp_path):
    # Create a simple PNG file
    arr = np.array([[0, 255], [128, 64]], dtype=np.uint8)
    img = Image.fromarray(arr)
    png_path = tmp_path / "test.png"
    img.save(png_path)

    checker = PngProfiler()
    report = checker.probe(png_path)
    assert report["file_type"] == "png"
    assert report["shape"] == (2, 2)
    assert report["min"] == 0
    assert report["max"] == 255
    assert report["nans"] == 0
    assert report["infs"] == 0
    assert report["unique"] == 4
