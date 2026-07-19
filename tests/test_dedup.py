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


def test_mode_exact_skips_text_and_image_detection():
    """mode='exact' must not compute (or return) text/image near-duplicates.

    Regression test: `mode` used to be a dead parameter — text and image
    near-duplicate detection (both O(n^2)) ran unconditionally regardless
    of what was requested, which could turn a cheap exact-only lookup into
    a call that takes a very long time on a dataset with many images/text
    files.
    """
    with tempfile.TemporaryDirectory() as td:
        p1 = os.path.join(td, "a.txt")
        p2 = os.path.join(td, "b.txt")
        with open(p1, "w") as f:
            f.write("hello world")
        with open(p2, "w") as f:
            f.write("hello world")

        res = dedup.find_duplicates([p1, p2], mode="exact", text_threshold=0.0)
        assert len(res["exact"]) == 1
        # text_threshold=0.0 would otherwise group these as near-duplicate
        # text too; mode="exact" must skip that computation entirely.
        assert res["text"] == []
        assert res["image"] == []


def test_mode_text_skips_image_detection():
    if dedup.Image is None:
        return
    from PIL import Image

    with tempfile.TemporaryDirectory() as td:
        p1 = os.path.join(td, "a.png")
        p2 = os.path.join(td, "b.png")
        img = Image.new("RGB", (16, 16), color=(255, 0, 0))
        img.save(p1)
        img.save(p2)

        res = dedup.find_duplicates([p1, p2], mode="text")
        assert res["image"] == []


def test_mode_auto_computes_all_categories():
    """Default behavior (mode='auto') must be unchanged: all three categories computed."""
    with tempfile.TemporaryDirectory() as td:
        p1 = os.path.join(td, "a.txt")
        p2 = os.path.join(td, "b.txt")
        with open(p1, "w") as f:
            f.write("the quick brown fox jumps over the lazy dog")
        with open(p2, "w") as f:
            f.write("the quick brown fox jumped over the lazy dog")

        res = dedup.find_duplicates([p1, p2], text_threshold=0.5)
        assert len(res["text"]) >= 1


def test_summarize_duplicate_directories_finds_mirrored_folders():
    """Two directory trees that mirror each other should surface as one high-overlap pair."""
    groups = [
        ["data/test/a.jpg", "data/mirror/test/a.jpg"],
        ["data/test/b.jpg", "data/mirror/test/b.jpg"],
        ["data/test/c.jpg", "data/mirror/test/c.jpg"],
    ]
    all_paths = [
        "data/test/a.jpg",
        "data/test/b.jpg",
        "data/test/c.jpg",
        "data/mirror/test/a.jpg",
        "data/mirror/test/b.jpg",
        "data/mirror/test/c.jpg",
    ]

    result = dedup.summarize_duplicate_directories(groups, all_paths=all_paths)

    assert len(result) == 1
    pair = result[0]
    assert {pair["dir_a"], pair["dir_b"]} == {"data/test", "data/mirror/test"}
    assert pair["shared_files"] == 3
    assert pair["dir_a_total_files"] == 3
    assert pair["dir_b_total_files"] == 3
    assert pair["overlap_pct"] == 100.0


def test_summarize_duplicate_directories_without_all_paths_omits_pct():
    groups = [["a/1.txt", "b/1.txt"]]
    result = dedup.summarize_duplicate_directories(groups)

    assert len(result) == 1
    assert result[0]["shared_files"] == 1
    assert result[0]["dir_a_total_files"] is None
    assert result[0]["overlap_pct"] is None


def test_summarize_duplicate_directories_respects_min_shared():
    groups = [["a/1.txt", "b/1.txt"]]  # only 1 shared file between a/ and b/
    result = dedup.summarize_duplicate_directories(groups, min_shared=2)
    assert result == []


def test_summarize_duplicate_directories_sorted_by_shared_files_desc():
    groups = [
        ["a/1.txt", "b/1.txt"],
        ["c/1.txt", "d/1.txt"],
        ["c/2.txt", "d/2.txt"],
        ["c/3.txt", "d/3.txt"],
    ]
    result = dedup.summarize_duplicate_directories(groups)
    assert result[0]["shared_files"] == 3
    assert {result[0]["dir_a"], result[0]["dir_b"]} == {"c", "d"}
    assert result[1]["shared_files"] == 1


def test_summarize_duplicate_directories_handles_three_way_group():
    """A group spanning 3 directories should contribute to all 3 pairs."""
    groups = [["a/1.txt", "b/1.txt", "c/1.txt"]]
    result = dedup.summarize_duplicate_directories(groups)
    assert len(result) == 3
    pairs = {frozenset((r["dir_a"], r["dir_b"])) for r in result}
    assert pairs == {frozenset(("a", "b")), frozenset(("a", "c")), frozenset(("b", "c"))}


def test_summarize_duplicate_directories_empty_input():
    assert dedup.summarize_duplicate_directories([]) == []
