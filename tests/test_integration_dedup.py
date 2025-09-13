import os
import tempfile

from filoma.files.file_profiler import FileProfiler
from filoma.images.image_profiler import ImageProfiler


def test_file_profiler_fingerprint_text():
    fp = FileProfiler()
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "a.txt")
        with open(p, "w") as f:
            f.write("one two three four five")
        info = fp.fingerprint_for_dedup(p, compute_text=True)
        assert info["path"] == p
        assert info["sha256"] is not None
        assert isinstance(info["text_shingles"], set)


def test_image_profiler_hash_optional():
    ip = ImageProfiler()
    # If Pillow not installed the call should raise; skip test in that case
    try:
        from PIL import Image
    except Exception:
        return

    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "a.png")
        img = Image.new("RGB", (16, 16), color=(0, 255, 0))
        img.save(p)
        h = ip.compute_ahash(p)
        assert isinstance(h, str)
