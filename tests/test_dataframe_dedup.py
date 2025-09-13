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
