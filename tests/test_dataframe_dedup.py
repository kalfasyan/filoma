import os
import tempfile

from filoma.dataframe import DataFrame


def test_dataframe_evaluate_duplicates_text():
    with tempfile.TemporaryDirectory() as td:
        p1 = os.path.join(td, "a.txt")
        p2 = os.path.join(td, "b.txt")
        with open(p1, "w") as f:
            f.write("the quick brown fox jumps over the lazy dog")
        with open(p2, "w") as f:
            f.write("the quick brown fox jumped over the lazy dog")

        df = DataFrame([p1, p2])
        res = df.evaluate_duplicates(text_threshold=0.4, show_table=False)
        assert "text" in res
        assert len(res["text"]) >= 1


def test_dataframe_evaluate_duplicates_mode_exact_skips_text():
    """mode='exact' must skip the O(n^2) text near-duplicate pass entirely."""
    with tempfile.TemporaryDirectory() as td:
        p1 = os.path.join(td, "a.txt")
        p2 = os.path.join(td, "b.txt")
        with open(p1, "w") as f:
            f.write("the quick brown fox jumps over the lazy dog")
        with open(p2, "w") as f:
            f.write("the quick brown fox jumped over the lazy dog")

        df = DataFrame([p1, p2])
        res = df.evaluate_duplicates(text_threshold=0.4, show_table=False, mode="exact")
        assert res["text"] == []
        assert res["image"] == []


def test_dataframe_evaluate_duplicates_reuses_is_file_column():
    """When an `is_file` column already exists, it must be reused instead of re-stat'ing every path."""
    with tempfile.TemporaryDirectory() as td:
        p1 = os.path.join(td, "a.txt")
        p2 = os.path.join(td, "b.txt")
        with open(p1, "w") as f:
            f.write("same content")
        with open(p2, "w") as f:
            f.write("same content")

        df = DataFrame([p1, p2]).add_file_stats_cols()
        assert "is_file" in df.columns

        res = df.evaluate_duplicates(show_table=False, mode="exact")
        assert len(res["exact"]) == 1
        assert set(res["exact"][0]) == {p1, p2}


def test_add_duplicate_cols_flags_exact_duplicates():
    with tempfile.TemporaryDirectory() as td:
        p1 = os.path.join(td, "a.txt")
        p2 = os.path.join(td, "b.txt")
        p3 = os.path.join(td, "c.txt")
        with open(p1, "w") as f:
            f.write("identical content")
        with open(p2, "w") as f:
            f.write("identical content")
        with open(p3, "w") as f:
            f.write("different content")

        df = DataFrame([p1, p2, p3])
        result = df.add_duplicate_cols()
        pdf = result.to_polars()

        assert set(pdf.columns) >= {"is_exact_duplicate", "exact_dup_group_id"}

        flags = dict(zip(pdf["path"].to_list(), pdf["is_exact_duplicate"].to_list()))
        assert flags[p1] is True
        assert flags[p2] is True
        assert flags[p3] is False

        group_ids = dict(zip(pdf["path"].to_list(), pdf["exact_dup_group_id"].to_list()))
        assert group_ids[p1] == group_ids[p2]
        assert group_ids[p3] is None


def test_add_duplicate_cols_recomputes_null_hash_column():
    """A pre-existing but unpopulated sha256 column (e.g. from enrich=True
    without compute_hash) must be recomputed, not silently trusted."""
    with tempfile.TemporaryDirectory() as td:
        p1 = os.path.join(td, "a.txt")
        p2 = os.path.join(td, "b.txt")
        with open(p1, "w") as f:
            f.write("same")
        with open(p2, "w") as f:
            f.write("same")

        df = DataFrame([p1, p2])
        df = df.add_file_stats_cols(compute_hash=False)  # sha256 column exists but is all-null
        result = df.add_duplicate_cols()
        pdf = result.to_polars()

        assert pdf["sha256"].null_count() == 0
        assert all(pdf["is_exact_duplicate"].to_list())


def test_add_corruption_cols_flags_zero_byte_and_corrupt_image():
    with tempfile.TemporaryDirectory() as td:
        zero_byte = os.path.join(td, "empty.txt")
        with open(zero_byte, "w"):
            pass

        fake_image = os.path.join(td, "broken.jpg")
        with open(fake_image, "w") as f:
            f.write("not actually a jpeg")

        healthy = os.path.join(td, "fine.txt")
        with open(healthy, "w") as f:
            f.write("all good here")

        df = DataFrame([zero_byte, fake_image, healthy])
        result = df.add_corruption_cols()
        pdf = result.to_polars()

        assert set(pdf.columns) >= {"is_corrupt", "corruption_reason"}

        reasons = dict(zip(pdf["path"].to_list(), pdf["corruption_reason"].to_list()))
        assert reasons[zero_byte] == "zero_byte"
        assert reasons[fake_image] == "corrupt_or_unsupported"
        assert reasons[healthy] is None

        flags = dict(zip(pdf["path"].to_list(), pdf["is_corrupt"].to_list()))
        assert flags[zero_byte] is True
        assert flags[fake_image] is True
        assert flags[healthy] is False


def test_add_corruption_cols_reuses_existing_size_bytes():
    """When size_bytes is already enriched, no extra stat() call should be
    needed to detect a zero-byte file."""
    with tempfile.TemporaryDirectory() as td:
        zero_byte = os.path.join(td, "empty.txt")
        with open(zero_byte, "w"):
            pass

        df = DataFrame([zero_byte]).add_file_stats_cols()
        assert "size_bytes" in df.df.columns

        result = df.add_corruption_cols()
        assert result.to_polars()["is_corrupt"][0] is True
