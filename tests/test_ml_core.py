import polars as pl
import pytest
from loguru import logger

from filoma import ml
from filoma.ml import _maybe_log_ratio_drift  # internal helper (acceptable for focused test)


def test_discover_filename_features_tokens_parent_parts():
    df = pl.DataFrame(
        {
            "path": [
                "A/B/SITE1_type_001.txt",
                "A/B/SITE2_type_002.txt",
            ]
        }
    )
    out = ml.discover_filename_features(
        df,
        sep="_",
        prefix=None,
        include_parent=True,
        include_all_parts=True,
        path_col="path",
    )
    # Basic expected columns
    for col in ["token1", "token2", "token3", "parent", "path_part0"]:
        assert col in out.columns
    # Tokens extracted correctly
    first_tokens = out.select("token1").to_series().to_list()
    assert first_tokens == ["SITE1", "SITE2"]


def test_auto_split_deterministic_with_seed():
    paths = [f"root/dir/file_{i}.txt" for i in range(30)]
    df = pl.DataFrame({"path": paths})
    t1, v1, te1 = ml.auto_split(df, train_val_test=(60, 20, 20), seed=123, path_col="path")
    t2, v2, te2 = ml.auto_split(df, train_val_test=(60, 20, 20), seed=123, path_col="path")
    # Deterministic membership
    assert set(t1["path"].to_list()) == set(t2["path"].to_list())
    assert set(v1["path"].to_list()) == set(v2["path"].to_list())
    assert set(te1["path"].to_list()) == set(te2["path"].to_list())


def test_auto_split_parts_parent_grouping():
    # Group by parent folder using parts index -2 (second last part) for deeply nested paths
    paths = [
        "data/classA/a_1.txt",
        "data/classA/a_2.txt",
        "data/classB/b_1.txt",
        "data/classB/b_2.txt",
    ]
    df = pl.DataFrame({"path": paths})
    # Use parent grouping via parts (-2 gives the immediate parent 'classA'/'classB')
    train, val, test = ml.auto_split(df, train_val_test=(50, 25, 25), parts=(-2,), path_col="path")

    # Ensure no group is split across multiple sets
    def collect_groups(d):
        return {p.split("/")[-2] for p in d["path"].to_list()} if len(d) else set()

    g_train, g_val, g_test = map(collect_groups, (train, val, test))
    # Intersections must be empty
    assert g_train.isdisjoint(g_val)
    assert g_train.isdisjoint(g_test)
    assert g_val.isdisjoint(g_test)


def test_auto_split_invalid_path_column():
    df = pl.DataFrame({"p": ["a/b/c.txt"]})
    with pytest.raises(ValueError):
        ml.auto_split(df, path_col="path")  # missing column


def test_internal_warning_helper_triggers():
    # Directly exercise internal drift logger to avoid depending on probabilistic splits
    messages = []
    sink_id = logger.add(lambda m: messages.append(m), level="WARNING")
    try:
        # Requested ratios 60/20/20 but achieved counts 10/0/0 -> large drift
        _maybe_log_ratio_drift(10, 0, 0, 10, (0.6, 0.2, 0.2), True)
    finally:
        logger.remove(sink_id)
    assert any("auto_split" in str(m) for m in messages)


def test_auto_split_empty_dataframe():
    # Empty path column (ensure string dtype)
    df = pl.DataFrame({"path": pl.Series("path", [], dtype=pl.Utf8)})
    train, val, test = ml.auto_split(df, train_val_test=(60, 20, 20), path_col="path", seed=0)
    assert len(train) == 0 and len(val) == 0 and len(test) == 0
    # Ensure feature column still added (with zero rows)
    assert any(col.startswith("_feat_") for col in train.columns)


def test_all_files_identical_stem_one_group():
    # Two files same filename in different dirs -> same feature, must stay together
    df = pl.DataFrame(
        {
            "path": [
                "dirA/shared_name.txt",
                "dirB/shared_name.txt",
            ]
        }
    )
    train, val, test = ml.auto_split(df, train_val_test=(50, 25, 25), how="stem", seed=7)
    lens = [len(train), len(val), len(test)]
    assert sorted(lens) == [0, 0, 2]  # exactly one split got both rows


def test_extremely_unbalanced_ratios():
    df = pl.DataFrame({"path": [f"p/file_{i}.txt" for i in range(40)]})
    train, val, test = ml.auto_split(df, train_val_test=(99, 1, 0), seed=123)
    # No test rows expected (ratio for test is zero after normalization)
    assert len(test) == 0
    assert len(train) + len(val) == 40
    # Val should be small (could be zero or a few depending on hash, but not large)
    assert len(val) <= 2


def test_pandas_return_type_conversion():
    pd = pytest.importorskip("pandas")
    try:
        import pyarrow  # noqa: F401
    except ImportError:
        pytest.skip("pyarrow required for polars -> pandas conversion")
    df = pl.DataFrame({"path": ["a/x_1.txt", "b/y_2.txt", "c/z_3.txt"]})
    df2 = ml.discover_filename_features(df, sep="_", prefix=None, path_col="path")
    tr, va, te = ml.auto_split(df2, train_val_test=(60, 20, 20), path_col="path", seed=0, return_type="pandas")
    for part in (tr, va, te):
        assert isinstance(part, pd.DataFrame)
        assert "path" in part.columns


def test_filoma_dataframe_auto_split_wrapper():
    from filoma.dataframe import DataFrame as FDF

    paths = [f"dir/sub/file_{i}.txt" for i in range(12)]
    fdf = FDF(pl.DataFrame({"path": paths}))
    train, val, test = fdf.auto_split(train_val_test=(60, 20, 20), seed=0)
    # Should return filoma.DataFrame wrappers by default
    for part in (train, val, test):
        assert hasattr(part, "df")
        assert isinstance(part.df, pl.DataFrame)
    # Check deterministic repeat
    train2, val2, test2 = fdf.auto_split(train_val_test=(60, 20, 20), seed=0)
    assert set(train.df["path"].to_list()) == set(train2.df["path"].to_list())
