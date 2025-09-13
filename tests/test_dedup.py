import os
import tempfile

from filoma import dedup


def test_compute_sha256_and_exact():
    with tempfile.TemporaryDirectory() as td:
        p1 = os.path.join(td, "a.txt")
        p2 = os.path.join(td, "b.txt")
        with open(p1, "w") as f:
            f.write("hello world")
        with open(p2, "w") as f:
            f.write("hello world")
        res = dedup.find_duplicates([p1, p2])
        assert len(res["exact"]) == 1
        assert set(res["exact"][0]) == {p1, p2}


def test_text_similarity():
    with tempfile.TemporaryDirectory() as td:
        p1 = os.path.join(td, "a.txt")
        p2 = os.path.join(td, "b.txt")
        with open(p1, "w") as f:
            f.write("the quick brown fox jumps over the lazy dog")
        with open(p2, "w") as f:
            f.write("the quick brown fox jumped over the lazy dog")
        res = dedup.find_duplicates([p1, p2], text_threshold=0.5)
        assert len(res["text"]) >= 1


def test_image_hashing_optional():
    # If Pillow not installed, this test is skipped
    if dedup.Image is None:
        return
    from PIL import Image

    with tempfile.TemporaryDirectory() as td:
        p1 = os.path.join(td, "a.png")
        p2 = os.path.join(td, "b.png")
        img = Image.new("RGB", (16, 16), color=(255, 0, 0))
        img.save(p1)
        img.save(p2)
        res = dedup.find_duplicates([p1, p2])
        assert len(res["image"]) >= 1
