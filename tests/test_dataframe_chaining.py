import polars as pl

from filoma.dataframe import DataFrame


def test_chaining_filter_depth_group_by_extension(tmp_path):
    # Create sample files and directories
    p = tmp_path
    (p / "a").mkdir()
    (p / "a" / "one.py").write_text("print(1)")
    (p / "a" / "two.txt").write_text("hello")
    (p / "b").mkdir()
    (p / "b" / "three.py").write_text("print(2)")

    # Build initial filoma.DataFrame from paths
    paths = [str(p / "a" / "one.py"), str(p / "a" / "two.txt"), str(p / "b" / "three.py")]
    df = DataFrame(paths)

    # Chain operations: filter_by_extension -> add_depth_col -> group_by_extension
    chained = df.filter_by_extension(".py").add_depth_col(path=p).group_by_extension()

    # group_by_extension should return a filoma.DataFrame wrapper
    assert isinstance(chained, DataFrame)

    # Convert to polars and check expected extensions and counts
    pl_df = chained.to_polars()
    assert "extension" in pl_df.columns
    assert "len" in pl_df.columns

    # Python files count should be 2
    py_row = pl_df.filter(pl.col("extension") == ".py")
    assert py_row.select(pl.col("len")).to_series()[0] == 2
