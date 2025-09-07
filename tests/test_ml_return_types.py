import polars as pl
import pytest

from filoma import ml


def test_return_type_filoma():
    paths = [
        "X/Y/A_1_01.txt",
        "X/Y/A_1_02.txt",
        "Z/W/B_2_01.txt",
    ]
    df = pl.DataFrame({"path": paths})

    # discover tokens so token1 exists
    df2 = ml.discover_filename_features(df, sep="_", prefix=None, include_parent=True, path_col="path")

    tr, va, te = ml.auto_split(df2, train_val_test=(60, 20, 20), path_col="path", return_type="filoma", seed=0)

    # filoma.DataFrame wrapper exposes .df property with a Polars DataFrame
    for part in (tr, va, te):
        assert hasattr(part, "df")
        assert isinstance(part.df, pl.DataFrame)


def test_return_type_pandas():
    pd = pytest.importorskip("pandas")

    paths = [
        "X/Y/A_1_01.txt",
        "X/Y/A_1_02.txt",
        "Z/W/B_2_01.txt",
    ]
    df = pl.DataFrame({"path": paths})

    df2 = ml.discover_filename_features(df, sep="_", prefix=None, include_parent=True, path_col="path")

    tr, va, te = ml.auto_split(df2, train_val_test=(60, 20, 20), path_col="path", return_type="pandas", seed=0)

    # Ensure pandas.DataFrame objects returned
    assert isinstance(tr, pd.DataFrame)
    assert isinstance(va, pd.DataFrame)
    assert isinstance(te, pd.DataFrame)

    # Check columns include token1
    assert "token1" in tr.columns
