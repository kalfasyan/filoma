import polars as pl

from filoma import ml


def test_multi_column_grouping_keeps_rows_together():
    # Create data where grouping on (user, session) should keep pairs together
    df = pl.DataFrame(
        {
            "path": [
                "u1/s1/file_a.txt",
                "u1/s1/file_b.txt",
                "u1/s2/file_c.txt",
                "u2/s3/file_d.txt",
                "u2/s3/file_e.txt",
            ],
            "user": ["u1", "u1", "u1", "u2", "u2"],
            "session": ["s1", "s1", "s2", "s3", "s3"],
        }
    )

    tr, va, te = ml.split_data(df, train_val_test=(60, 20, 20), feature=("user", "session"), path_col="path", seed=0)

    # No group should be split across sets: collect (user,session) per split
    def groups(d):
        return {"/".join(p.split("/")[:2]) for p in d["path"].to_list()} if len(d) else set()

    gtr, gva, gte = map(groups, (tr, va, te))
    assert gtr.isdisjoint(gva)
    assert gtr.isdisjoint(gte)
    assert gva.isdisjoint(gte)


def test_path_parts_negative_and_positive_indices():
    paths = [
        "root/a/b/c/file1.txt",
        "root/a/b/d/file2.txt",
        "root/a/b/z/file3.txt",
    ]
    df = pl.DataFrame({"path": paths})

    # Use last part (filename) explicitly and via default
    t1, v1, te1 = ml.split_data(df, train_val_test=(60, 20, 20), feature="path_parts", path_parts=(-1,), path_col="path", seed=1)
    # Use positive index 4 (0-based parts: ['root','a','b','c','file1.txt'])
    t2, v2, te2 = ml.split_data(df, train_val_test=(60, 20, 20), feature="path_parts", path_parts=(4,), path_col="path", seed=1)

    # The two ways of selecting the same part should produce identical groupings
    assert set(t1["path"].to_list()) == set(t2["path"].to_list())
    assert set(v1["path"].to_list()) == set(v2["path"].to_list())
    assert set(te1["path"].to_list()) == set(te2["path"].to_list())


def test_feature_preview_columns_added():
    df = pl.DataFrame({"path": ["a/b/c.txt", "d/e/f.txt"]})

    # path_parts preview
    tr, va, te = ml.split_data(df, train_val_test=(60, 20, 20), feature="path_parts", path_parts=(-1,), path_col="path", seed=0)
    assert any(col.startswith("_feat_") for col in tr.columns)

    # column-based preview when grouping by token: create a token column
    df2 = df.with_columns([pl.lit("A").alias("token1")])
    tr2, _, _ = ml.split_data(df2, train_val_test=(60, 20, 20), feature="token1", path_col="path", seed=0)
    assert "_feat_group" in tr2.columns
