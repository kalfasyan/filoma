import polars as pl

from filoma.ml import split_data


def _make_df(n_groups: int = 10, per_group: int = 10):
    paths = []
    for g in range(n_groups):
        for i in range(per_group):
            paths.append(f"grp{g}/file{i}.txt")
    return pl.DataFrame({"path": paths})


def _collect_paths(dfs_tuple):
    t, v, te = dfs_tuple
    return tuple([tuple(df["path"].to_list()) for df in (t, v, te)])


def test_deterministic_with_same_seed():
    df = _make_df(n_groups=8, per_group=5)
    out1 = split_data(df, train_val_test=(70, 15, 15), feature="path_parts", path_parts=(-2,), seed=42)
    out2 = split_data(df, train_val_test=(70, 15, 15), feature="path_parts", path_parts=(-2,), seed=42)
    assert _collect_paths(out1) == _collect_paths(out2)


def test_random_state_overrides_seed():
    df = _make_df(n_groups=8, per_group=5)
    out_seed = split_data(df, train_val_test=(70, 15, 15), feature="path_parts", path_parts=(-2,), seed=1)
    out_random = split_data(df, train_val_test=(70, 15, 15), feature="path_parts", path_parts=(-2,), seed=1, random_state=7)
    out_effective = split_data(df, train_val_test=(70, 15, 15), feature="path_parts", path_parts=(-2,), seed=7)
    # random_state should match behavior as if seed were equal to random_state
    assert _collect_paths(out_random) == _collect_paths(out_effective)
    # and should differ from the original seed=1 run
    assert _collect_paths(out_seed) != _collect_paths(out_random)


def test_different_seeds_produce_different_splits():
    df = _make_df(n_groups=8, per_group=5)
    out1 = split_data(df, train_val_test=(70, 15, 15), feature="path_parts", path_parts=(-2,), seed=2)
    out2 = split_data(df, train_val_test=(70, 15, 15), feature="path_parts", path_parts=(-2,), seed=3)
    assert _collect_paths(out1) != _collect_paths(out2)
