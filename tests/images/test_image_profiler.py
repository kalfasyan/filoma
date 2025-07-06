import numpy as np

from filoma.images.image_profiler import ImageProfiler


def test_analyze_basic_stats():
    arr = np.array([[1, 2, 3], [4, 5, 6]])
    profiler = ImageProfiler()
    report = profiler.analyze(arr)
    assert report["shape"] == (2, 3)
    assert report["dtype"] == "int64"
    assert report["min"] == 1
    assert report["max"] == 6
    assert report["mean"] == 3.5
    assert report["nans"] == 0
    assert report["infs"] == 0
    assert report["unique"] == 6

def test_analyze_with_nans_and_infs():
    arr = np.array([[np.nan, np.inf, 1], [2, 2, 3]])
    profiler = ImageProfiler()
    report = profiler.analyze(arr)
    assert report["nans"] == 1
    assert report["infs"] == 1
    assert report["unique"] >= 3

def test_analyze_empty_array():
    arr = np.array([])
    profiler = ImageProfiler()
    report = profiler.analyze(arr)
    assert report["shape"] == (0,)
    assert report["unique"] == 0
