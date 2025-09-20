import polars as pl

from filoma import ml
from filoma.dataframe import DataFrame as FDataFrame


def test_discover_and_split_with_custom_path_col():
    paths = [
        "A/B/ONE_TWO_01.txt",
        "A/B/ONE_TWO_02.txt",
        "C/D/TWO_ONE_01.txt",
    ]
    df = pl.DataFrame({"my_path": paths})

    # discover into token columns using custom column name via DataFrame API
    df2 = FDataFrame(df).add_filename_features(sep="_", prefix=None, include_parent=True, include_all_parts=True, path_col="my_path").df

    # expected columns present
    assert "token1" in df2.columns
    assert "token2" in df2.columns
    assert "parent" in df2.columns
    assert "path_part0" in df2.columns

    # splitting by token1 should run and return 3 dataframes
    tr, va, te = ml.split_data(df2, train_val_test=(60, 20, 20), path_col="my_path", seed=0)
    assert isinstance(tr, (pl.DataFrame, FDataFrame))
    assert isinstance(va, (pl.DataFrame, FDataFrame))
    assert isinstance(te, (pl.DataFrame, FDataFrame))
