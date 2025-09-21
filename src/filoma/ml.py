"""Simple ML-style utilities for filoma DataFrame splitting.

Provides an intuitive split_data API to split a filoma.DataFrame into train/val/test
based on filename/path-derived features. The goal is a tiny, dependency-free,
user-friendly interface using pathlib.Path to select path parts.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Iterable, List, Optional, Sequence, Tuple, Union

import polars as pl
from loguru import logger


def _normalize_ratios(ratios: Sequence[float]) -> List[float]:
    """Normalize train/val/test ratios.

    Accepts either integers summing to 100 (percents), floats summing to 1,
    or any positive numbers which will be normalized by their sum.
    """
    total = sum(ratios)
    if total <= 0:
        raise ValueError("Ratios must sum to a positive value")

    # If user passed percentages that sum to 100
    if abs(total - 100.0) < 1e-8:
        return [float(r) / 100.0 for r in ratios]

    # If already fractional and sums to ~1
    if abs(total - 1.0) < 1e-8:
        return [float(r) for r in ratios]

    # Fallback: normalize by sum
    return [float(r) / total for r in ratios]


def _stable_hash(s: str, seed: Optional[int] = None) -> int:
    """Return a stable integer hash for a string. Optionally incorporate a seed."""
    m = hashlib.sha256()
    if seed is not None:
        m.update(str(seed).encode("utf-8"))
    m.update(s.encode("utf-8"))
    # Use 8 bytes to get a large integer
    return int.from_bytes(m.digest()[:8], "big")


def _get_feature_value(path_str: str, feature: str, path_parts: Optional[Iterable[int]] = None) -> str:
    p = Path(path_str)
    if feature == "path_parts":
        # path_parts is an iterable of part indices (negative allowed)
        if path_parts is None:
            raise ValueError("path_parts must be provided when feature='path_parts'")
        parts_list = list(path_parts)
        selected = []
        for idx in parts_list:
            try:
                selected.append(p.parts[idx])
            except IndexError:
                selected.append("")
        return "/".join(selected)
    elif feature == "filename":
        return p.name
    elif feature == "stem":
        return p.stem
    elif feature == "parent":
        return str(p.parent)
    elif feature == "suffix":
        return p.suffix
    else:
        raise ValueError(f"Unknown feature='{feature}'")


# NOTE: filename-feature discovery is provided as a method on
# `filoma.dataframe.DataFrame.add_filename_features`. We no longer expose a
# standalone `ml.add_filename_features` function to encourage using the
# DataFrame API which returns filoma.DataFrame wrappers.


# ------------ Internal helper functions for modular split_data ------------ #
def _maybe_discover(
    df_obj: Any,
    discover: bool,
    sep: str,
    feat_prefix: str,
    max_tokens: Optional[int],
    include_parent: bool,
    include_all_parts: bool,
    token_names: Optional[Union[str, Sequence[str]]],
    path_col: str,
) -> Any:
    """If `discover` is True, ensure filename-token columns exist and return a `filoma.DataFrame` wrapper.

    If `discover` is False, wrap the provided object in a `filoma.DataFrame` if necessary and return it unchanged.
    """
    if not discover:
        # If it's already a filoma.DataFrame just return it; otherwise wrap it
        from .dataframe import DataFrame as FDataFrame

        if hasattr(df_obj, "df"):
            return df_obj
        return FDataFrame(df_obj)

    # Use the filoma.DataFrame instance method for discovery to ensure we
    # consistently work with filoma.DataFrame wrappers. Wrap polars frames
    # when necessary and return the filoma.DataFrame result.
    from .dataframe import DataFrame as FDataFrame

    if hasattr(df_obj, "df"):
        base = df_obj
    else:
        base = FDataFrame(df_obj)

    res = base.add_filename_features(
        path_col=path_col,
        sep=sep,
        prefix=feat_prefix,
        max_tokens=max_tokens,
        include_parent=include_parent,
        include_all_parts=include_all_parts,
        token_names=token_names,
        enrich=False,
        inplace=False,
    )

    return res


def _build_feature_index(
    pl_df: pl.DataFrame,
    path_col: str,
    feature: Union[str, Sequence[str]],
    path_parts: Optional[Iterable[int]] = None,
) -> Tuple[dict, List[str]]:
    """Build a mapping from feature value -> list of row indices.

      `feature` may be:
          - a string in {'path_parts', 'filename', 'stem', 'parent', 'suffix'} ->
              derive feature from `path_col` using `_get_feature_value` (when
              'path_parts' use `path_parts`).
          - a string naming an existing DataFrame column -> group by that column.
    - a sequence of column names -> combine those column values to form the group key.
    """
    PATH_MODES = {"path_parts", "filename", "stem", "parent", "suffix"}
    mapping: dict = {}

    # Column-based grouping when feature is a sequence or a column name
    if isinstance(feature, (list, tuple)) or (isinstance(feature, str) and feature not in PATH_MODES and feature in pl_df.columns):
        if isinstance(feature, str):
            cols = [feature]
        else:
            cols = list(feature)

        col_lists = [pl_df[c].to_list() for c in cols]
        total = len(pl_df)
        for i in range(total):
            vals = []
            for col_list in col_lists:
                v = col_list[i]
                vals.append("") if v is None else vals.append(str(v))
            feat = "||".join(vals)
            mapping.setdefault(feat, []).append(i)

        paths = pl_df[path_col].to_list() if path_col in pl_df.columns else [""] * total
        return mapping, paths

    # Otherwise treat feature as a path-derived mode
    # Pass through the feature name directly; `_get_feature_value` expects
    # the canonical name 'path_parts' for parts-based extraction.
    how = feature
    paths = pl_df[path_col].to_list()
    for i, p in enumerate(paths):
        feat = _get_feature_value(p, feature=how, path_parts=path_parts)
        mapping.setdefault(feat, []).append(i)
    return mapping, paths


def _assign_features(feature_to_idxs: dict, ratios: Sequence[float], seed: Optional[int]) -> dict:
    assignment = {}
    r0, r1 = ratios[0], ratios[0] + ratios[1]
    for feat in feature_to_idxs:
        h = _stable_hash(feat, seed=seed)
        frac = (h % (10**8)) / 1e8
        if frac < r0:
            assignment[feat] = "train"
        elif frac < r1:
            assignment[feat] = "val"
        else:
            assignment[feat] = "test"
    return assignment


def _assign_features_by_mapping(feature_to_idxs: dict, split_mapping: dict) -> dict:
    """Assign features to splits based on explicit mapping."""
    assignment = {}
    unmapped_features = []

    for feat in feature_to_idxs:
        if feat in split_mapping:
            mapped_split = split_mapping[feat]
            if mapped_split not in {"train", "val", "test"}:
                raise ValueError(f"split_mapping values must be 'train', 'val', or 'test', got '{mapped_split}' for feature '{feat}'")
            assignment[feat] = mapped_split
        else:
            unmapped_features.append(feat)

    if unmapped_features:
        logger.warning(f"split_mapping: {len(unmapped_features)} feature(s) not found in mapping and will be excluded: {unmapped_features[:5]}...")

    return assignment


def _mask_from_assignment(feature_to_idxs: dict, feature_assignment: dict, total: int) -> List[str]:
    mask: List[str] = [None] * total  # type: ignore
    for feat, idxs in feature_to_idxs.items():
        if feat in feature_assignment:  # Only assign if feature is mapped
            split = feature_assignment[feat]
            for i in idxs:
                mask[i] = split  # type: ignore
        # If feat not in feature_assignment, those indices remain None and will be filtered out
    return mask


def _add_feature_column(
    pl_df: pl.DataFrame,
    path_col: str,
    feature: Union[str, Sequence[str]],
    path_parts: Optional[Iterable[int]] = None,
) -> pl.DataFrame:
    """Add a convenience column showing the feature used for splitting.

    For column-based features the column `_feat_group` is added. For
    path-derived features a column named `_feat_{feature}` is added (uses
    `_feat_path_parts` when `feature=='path_parts'`).
    """
    PATH_MODES = {"path_parts", "filename", "stem", "parent", "suffix"}

    if isinstance(feature, (list, tuple)) or (isinstance(feature, str) and feature not in PATH_MODES and feature in pl_df.columns):
        if isinstance(feature, str):
            cols = [feature]
        else:
            cols = list(feature)

        # Use Polars struct + map_elements to combine column values into a
        # single preview column. This avoids relying on concat_str semantics
        # which vary between Polars versions.
        def _combine(vals):
            return "||".join(("" if vals.get(c) is None else str(vals.get(c))) for c in cols)

        struct_expr = pl.struct([pl.col(c).alias(c) for c in cols])
        return pl_df.with_columns([struct_expr.map_elements(_combine, return_dtype=pl.Utf8).alias("_feat_group")])

    # path-derived: pass the canonical feature name through ('path_parts' etc.)
    how = feature
    feat_name = "_feat_path_parts" if feature == "path_parts" else f"_feat_{feature}"
    return pl_df.with_columns(
        [
            pl.col(path_col)
            .map_elements(
                lambda x: _get_feature_value(x, feature=how, path_parts=path_parts),
                return_dtype=pl.Utf8,
            )
            .alias(feat_name)
        ]
    )


def _maybe_log_ratio_drift(
    train_n: int,
    val_n: int,
    test_n: int,
    total: int,
    ratios: Sequence[float],
    verbose: bool,
):
    if not verbose or total == 0:
        return
    req = ratios
    act_counts = (train_n, val_n, test_n)
    act = tuple(c / total for c in act_counts)
    if any(abs(a - r) > max(1 / total, 0.05) for a, r in zip(act, req)):
        req_pct = ",".join(f"{r * 100:.1f}%" for r in req)
        act_pct = ",".join(f"{a * 100:.1f}%" for a in act)
        logger.warning(
            f"filoma.ml.split_data: achieved counts {act_pct} ({act_counts}) vs requested ({req_pct}) total={total} (grouped hashing can cause drift)"
        )


def split_data(
    data: Union[pl.DataFrame, Any],
    train_val_test: Tuple[float, float, float] = (80, 10, 10),
    feature: Union[str, Sequence[str]] = "path_parts",
    path_parts: Optional[Iterable[int]] = (-1,),
    seed: Optional[int] = None,
    random_state: Optional[int] = None,
    discover: bool = False,
    sep: str = "_",
    feat_prefix: str = "feat",
    max_tokens: Optional[int] = None,
    include_parent: bool = False,
    include_all_parts: bool = False,
    token_names: Optional[Union[str, Sequence[str]]] = None,
    path_col: str = "path",
    verbose: bool = True,
    validate_counts: bool = True,
    return_type: str = "filoma",
    split_mapping: Optional[dict] = None,
    files_only: bool = True,
) -> Tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """Split a filoma DataFrame into train/val/test based on filename/path-derived features.

    Parameters
    ----------
    data : Union[pl.DataFrame, Any]
        A Polars DataFrame or filoma.DataFrame wrapper containing a 'path' column.
    train_val_test : tuple[float, float, float]
        Three integers or ratios for train/val/test; they will be normalized to fractions.
    feature : Union[str, Sequence[str]]
        Which feature to use for grouping. May be a sequence of column names
        (group by existing columns), a single column name string, or one of
        'path_parts', 'filename', 'stem', 'parent', 'suffix' to derive the feature from `path_col`.
    path_parts : Optional[Iterable[int]]
        Iterable selecting indices in Path.parts (supports negative indices). Only used
        when `feature=='path_parts'`. Default picks -1 (filename).
    seed : Optional[int]
        Optional integer to alter hashing for reproducible, different splits.
    random_state : Optional[int]
        Alias for `seed` (if provided it takes precedence).
    discover : bool
        If True, automatically discover filename tokens and add columns named
        `prefix1`, `prefix2`, ... (or `token1`... if prefix=None).
    sep : str
        Separator used to split filename stems when `discover=True`.
    feat_prefix : str
        Prefix to use for discovered token column names. If None, names will be
        `token1`, `token2`, ...
    token_names : Optional[Union[str, Sequence[str]]]
        Optional list of column names to use for tokens, or 'auto' to automatically
        generate readable names (uses prefix if set).
    max_tokens : Optional[int]
        Maximum number of tokens to extract when discovering.
    include_parent : bool
        If True, add a `parent` column with the immediate parent folder name.
    include_all_parts : bool
        If True, add columns `path_part0`, `path_part1`, ... for all Path.parts.
    verbose : bool
        If True (default) log a short warning when achieved split counts differ noticeably
        from requested ratios (common with small datasets or grouped features).
    validate_counts : bool
        If True, log a warning when the set of unique feature values (or combined-column
        feature) is not identical across the train/val/test splits.
    return_type : str
        One of 'polars' (default), 'filoma' (wrap Polars into filoma.DataFrame), or
        'pandas' (convert to pandas.DataFrame). If 'pandas' is chosen, pandas must be available.
    split_mapping : Optional[dict]
        If provided, maps feature values to specific splits instead of using ratios.
        Keys should be feature values (e.g., folder names), values should be 'train', 'val', or 'test'.
        Example: {'training': 'train', 'validation': 'val', 'testing': 'test'}.
        When used, train_val_test ratios are ignored.
    files_only : bool
        If True (default), filter out directories and keep only files before splitting.
        Looks for 'is_file' column in the DataFrame. If the column doesn't exist,
        this parameter is ignored.
    path_col : str
        Column name in the input DataFrame containing file paths used for deriving features.

    Returns
    -------
            tuple: (train_df, val_df, test_df) as Polars DataFrames.

        Note:
            Splits are deterministic and grouped by the chosen feature to avoid
            leaking similar files into multiple sets when they share the same feature.
            The method uses sha256 hashing of the feature string to map to [0,1).

    """
    assert train_val_test is not None and len(train_val_test) == 3, "train_val_test must be a tuple of three numbers"

    # Accept filoma.DataFrame wrapper or raw Polars DataFrame; discovery
    # (if requested) will wrap raw frames into filoma.DataFrame. Defer the
    # `path_col` existence check until after discovery to avoid unwrapping
    # the filoma.DataFrame more than once.

    ratios = _normalize_ratios(train_val_test)

    # Discovery: return a filoma.DataFrame wrapper (or wrap the input if not discovering)
    df_work = _maybe_discover(
        data,
        discover=discover,
        sep=sep,
        feat_prefix=feat_prefix,
        max_tokens=max_tokens,
        include_parent=include_parent,
        include_all_parts=include_all_parts,
        token_names=token_names,
        path_col=path_col,
    )

    # Extract the underlying Polars DataFrame for downstream processing
    pl_work = df_work.df

    # Filter to files only if requested and column exists
    if files_only and "is_file" in pl_work.columns:
        original_count = len(pl_work)
        pl_work = pl_work.filter(pl.col("is_file"))
        files_count = len(pl_work)
        if verbose and original_count > files_count:
            logger.info(f"Filtered to files only: {files_count:,} files (removed {original_count - files_count:,} directories)")

    if path_col not in pl_work.columns:
        raise ValueError(f"DataFrame must have a '{path_col}' column")

    # Feature grouping & assignment
    feature_to_idxs, paths = _build_feature_index(pl_work, path_col=path_col, feature=feature, path_parts=path_parts)

    # Choose assignment method based on whether split_mapping is provided
    if split_mapping is not None:
        feature_assignment = _assign_features_by_mapping(feature_to_idxs, split_mapping)
    else:
        # Determine effective seed: prefer `random_state` if provided for sklearn-like API
        effective_seed = random_state if random_state is not None else seed
        feature_assignment = _assign_features(feature_to_idxs, ratios=ratios, seed=effective_seed)

    mask = _mask_from_assignment(feature_to_idxs, feature_assignment, total=len(paths))
    tmp = pl_work.with_columns([pl.Series("_split", mask)])

    # Feature column for user convenience
    tmp = _add_feature_column(tmp, path_col=path_col, feature=feature, path_parts=path_parts)

    # Split
    train_df = tmp.filter(pl.col("_split") == "train").drop("_split")
    val_df = tmp.filter(pl.col("_split") == "val").drop("_split")
    test_df = tmp.filter(pl.col("_split") == "test").drop("_split")

    # Validate that the unique feature values are represented equally across splits
    if validate_counts:
        PATH_MODES = {"path_parts", "filename", "stem", "parent", "suffix"}
        if isinstance(feature, (list, tuple)) or (isinstance(feature, str) and feature not in PATH_MODES and feature in pl_work.columns):
            feat_col = "_feat_group"
        else:
            feat_col = "_feat_path_parts" if feature == "path_parts" else f"_feat_{feature}"

        try:
            train_set = set(train_df[feat_col].to_list())
            val_set = set(val_df[feat_col].to_list())
            test_set = set(test_df[feat_col].to_list())
        except Exception:
            # If something unexpected happens (missing column), skip validation
            train_set = val_set = test_set = set()

        if not (train_set == val_set == test_set):
            union = train_set | val_set | test_set
            missing_in_train = list((union - train_set))[:5]
            missing_in_val = list((union - val_set))[:5]
            missing_in_test = list((union - test_set))[:5]
            logger.warning(
                (
                    "filoma.ml.split_data: unique feature values differ across splits for '{}' -"
                    " counts train={}, val={}, test={}; examples missing_in_train={},"
                    " missing_in_val={}, missing_in_test={}"
                ),
                feat_col,
                len(train_set),
                len(val_set),
                len(test_set),
                missing_in_train,
                missing_in_val,
                missing_in_test,
            )

    _maybe_log_ratio_drift(len(train_df), len(val_df), len(test_df), len(paths), ratios, verbose)

    # Return requested type (default: filoma.DataFrame wrappers)
    if return_type == "filoma" or return_type is None:
        # Lazy import filoma.DataFrame wrapper to avoid heavy imports at module import time
        try:
            from .dataframe import DataFrame as FDataFrame
        except Exception:
            from filoma.dataframe import DataFrame as FDataFrame

        return FDataFrame(train_df), FDataFrame(val_df), FDataFrame(test_df)

    if return_type == "polars":
        return train_df, val_df, test_df

    if return_type == "pandas":
        try:
            return train_df.to_pandas(), val_df.to_pandas(), test_df.to_pandas()
        except Exception as e:
            raise RuntimeError(f"Failed to convert to pandas DataFrame: {e}")

    raise ValueError(f"Unknown return_type='{return_type}'")
