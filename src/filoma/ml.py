"""
Simple ML-style utilities for filoma DataFrame splitting.

Provides an intuitive auto_split API to split a filoma.DataFrame into train/val/test
based on filename/path-derived features. The goal is a tiny, dependency-free,
user-friendly interface using pathlib.Path to select path parts.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Iterable, List, Optional, Sequence, Tuple, Union

import polars as pl
from loguru import logger


def _normalize_ratios(ratios: Sequence[int]) -> List[float]:
    total = sum(ratios)
    if total <= 0:
        raise ValueError("Ratios must sum to a positive value")
    return [r / total for r in ratios]


def _stable_hash(s: str, seed: Optional[int] = None) -> int:
    """Return a stable integer hash for a string. Optionally incorporate a seed."""
    m = hashlib.sha256()
    if seed is not None:
        m.update(str(seed).encode("utf-8"))
    m.update(s.encode("utf-8"))
    # Use 8 bytes to get a large integer
    return int.from_bytes(m.digest()[:8], "big")


def _get_feature_value(path_str: str, how: str, parts: Optional[Iterable[int]] = None) -> str:
    p = Path(path_str)
    if how == "parts":
        # parts is an iterable of part indices (negative allowed)
        if parts is None:
            raise ValueError("parts must be provided when how='parts'")
        parts_list = list(parts)
        selected = []
        for idx in parts_list:
            try:
                selected.append(p.parts[idx])
            except IndexError:
                selected.append("")
        return "/".join(selected)
    elif how == "filename":
        return p.name
    elif how == "stem":
        return p.stem
    elif how == "parent":
        return str(p.parent)
    elif how == "suffix":
        return p.suffix
    else:
        raise ValueError(f"Unknown how='{how}'")


def discover_filename_features(
    pl_df: pl.DataFrame,
    sep: str = "_",
    prefix: Optional[str] = "feat",
    max_tokens: Optional[int] = None,
    include_parent: bool = False,
    include_all_parts: bool = False,
    token_names: Optional[Union[str, Sequence[str]]] = None,
    path_col: str = "path",
) -> pl.DataFrame:
    """
    Discover separator-based tokens from filename stems and add them as columns.

    Args:
        pl_df: Polars DataFrame with a 'path' column.
        sep: separator to split the stem (default '_').
        prefix: prefix for generated feature columns (columns will be prefix1, prefix2, ...).
        max_tokens: optional max number of tokens to extract (otherwise uses observed max).
        include_parent: if True, add a 'parent' column containing the immediate parent folder name.

    Returns:
        Polars DataFrame with added feature columns.
    """
    if path_col not in pl_df.columns:
        raise ValueError(f"DataFrame must have a '{path_col}' column")

    # Extract stems and split by sep to discover token counts
    stems = [Path(s).stem for s in pl_df[path_col].to_list()]
    split_tokens = [stem.split(sep) if stem is not None else [""] for stem in stems]
    observed_max = max((len(t) for t in split_tokens), default=0)
    if max_tokens is None:
        max_tokens = observed_max

    # Normalize token_names
    # token_names may be: None, 'auto', or a sequence of names
    if token_names == "auto":
        token_names_seq = None
        auto_mode = True
    elif isinstance(token_names, (list, tuple)):
        token_names_seq = list(token_names)
        auto_mode = False
    else:
        token_names_seq = None
        auto_mode = False

    # For each token index create a column
    new_cols = []
    for i in range(max_tokens):
        # Decide column name: explicit token_names > prefix > generic token
        if token_names_seq is not None and i < len(token_names_seq) and token_names_seq[i]:
            col_name = token_names_seq[i]
        elif auto_mode:
            # auto generates readable token names using 'token' base or prefix if present
            base = prefix if prefix else "token"
            col_name = f"{base}{i + 1}"
        else:
            if prefix:
                col_name = f"{prefix}{i + 1}"
            else:
                col_name = f"token{i + 1}"

        def pick_token(s: str, idx=i):
            st = Path(s).stem
            parts = st.split(sep) if st is not None else [""]
            try:
                return parts[idx]
            except Exception:
                return ""

        new_cols.append(pl.col(path_col).map_elements(pick_token, return_dtype=pl.Utf8).alias(col_name))

    if include_parent:
        new_cols.append(pl.col(path_col).map_elements(lambda s: Path(s).parent.name, return_dtype=pl.Utf8).alias("parent"))

    # Optionally add all path parts as features (path_part0 is root/first part)
    if include_all_parts:
        parts_lists = [list(Path(s).parts) for s in pl_df[path_col].to_list()]
        max_parts = max((len(p) for p in parts_lists), default=0)
        for i in range(max_parts):
            col_name = f"path_part{i}"

            def pick_part(s: str, idx=i):
                try:
                    parts = list(Path(s).parts)
                    return parts[idx]
                except Exception:
                    return ""

            new_cols.append(pl.col(path_col).map_elements(pick_part, return_dtype=pl.Utf8).alias(col_name))

    return pl_df.with_columns(new_cols)


# ------------ Internal helper functions for modular auto_split ------------ #
def _maybe_discover(
    pl_df: pl.DataFrame,
    discover: bool,
    sep: str,
    feat_prefix: str,
    max_tokens: Optional[int],
    include_parent: bool,
    include_all_parts: bool,
    token_names: Optional[Union[str, Sequence[str]]],
    path_col: str,
) -> pl.DataFrame:
    if not discover:
        return pl_df
    return discover_filename_features(
        pl_df,
        sep=sep,
        prefix=feat_prefix,
        max_tokens=max_tokens,
        include_parent=include_parent,
        include_all_parts=include_all_parts,
        token_names=token_names,
        path_col=path_col,
    )


def _build_feature_index(pl_df: pl.DataFrame, path_col: str, how: str, parts: Optional[Iterable[int]]) -> Tuple[dict, List[str]]:
    paths = pl_df[path_col].to_list()
    mapping: dict = {}
    for i, p in enumerate(paths):
        feat = _get_feature_value(p, how=how, parts=parts)
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


def _mask_from_assignment(feature_to_idxs: dict, feature_assignment: dict, total: int) -> List[str]:
    mask: List[str] = [None] * total  # type: ignore
    for feat, idxs in feature_to_idxs.items():
        split = feature_assignment[feat]
        for i in idxs:
            mask[i] = split  # type: ignore
    return mask


def _add_feature_column(pl_df: pl.DataFrame, path_col: str, how: str, parts: Optional[Iterable[int]]) -> pl.DataFrame:
    feat_name = "_feat_parts" if how == "parts" else f"_feat_{how}"
    return pl_df.with_columns(
        [
            pl.col(path_col)
            .map_elements(
                lambda x: _get_feature_value(x, how=how, parts=parts),
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
            ("filoma.ml.auto_split: requested ratios {} -> achieved counts {} ({}) vs requested ({}) total={} (grouped hashing can cause drift)"),
            req_pct,
            act_counts,
            act_pct,
            req_pct,
            total,
        )


def auto_split(
    df: Union[pl.DataFrame, Any],
    train_val_test: Tuple[int, int, int] = (80, 10, 10),
    how: str = "parts",
    parts: Optional[Iterable[int]] = (-1,),
    seed: Optional[int] = None,
    discover: bool = False,
    sep: str = "_",
    feat_prefix: str = "feat",
    max_tokens: Optional[int] = None,
    include_parent: bool = False,
    include_all_parts: bool = False,
    token_names: Optional[Union[str, Sequence[str]]] = None,
    path_col: str = "path",
    verbose: bool = True,
    return_type: str = "polars",
) -> Tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """
    Split a filoma DataFrame into train/val/test based on filename/path-derived features.

    Args:
        df: a Polars DataFrame or filoma.DataFrame wrapper containing a 'path' column.
        train_val_test: three integers or ratios for train/val/test; they will be
                        normalized to fractions.
        how: which feature to derive from the path. Options: 'parts', 'filename',
             'stem', 'parent', 'suffix'. If 'parts', use the `parts` argument.
        parts: an iterable of integers selecting Path.parts indices (supports negative
               indices). Only used when how='parts'. Default picks -1 (filename).
        seed: optional integer to alter hashing for reproducible, different splits.
        discover: if True, automatically discover filename tokens and add columns
            named `prefix1`, `prefix2`, ... (or `token1`... if prefix=None).
        sep: separator used to split filename stems when `discover=True`.
        feat_prefix: prefix to use for discovered token column names. If None,
            discovered token columns will be named `token1`, `token2`, ...
        token_names: optional list of column names to use for tokens, or 'auto' to
                    automatically generate readable names (uses prefix if set).
        max_tokens: maximum number of tokens to extract when discovering.
        include_parent: if True, add a `parent` column with the immediate parent folder name.
        include_all_parts: if True, add columns `path_part0`, `path_part1`, ... for all Path.parts.
        verbose: if True (default) log a short warning when achieved split counts
            differ noticeably from requested ratios (common with small datasets or
            grouped features).
        return_type: one of 'polars' (default), 'filoma' (wrap Polars into filoma.DataFrame),
                or 'pandas' (convert to pandas.DataFrame). If 'pandas' is chosen,
                pandas must be available.

        Returns:
            (train_df, val_df, test_df) as Polars DataFrames.

        Notes:
            - Splits are deterministic and grouped by the chosen feature to avoid
            leaking similar files into multiple sets when they share the same feature.
            - The method uses sha256 hashing of the feature string to map to [0,1).
    """
    # Accept filoma.DataFrame wrapper or raw Polars DataFrame
    if hasattr(df, "df"):
        pl_df = df.df
    else:
        pl_df = df

    if path_col not in pl_df.columns:
        raise ValueError(f"DataFrame must have a '{path_col}' column")

    ratios = _normalize_ratios(train_val_test)

    # Discovery
    pl_work = _maybe_discover(
        pl_df,
        discover=discover,
        sep=sep,
        feat_prefix=feat_prefix,
        max_tokens=max_tokens,
        include_parent=include_parent,
        include_all_parts=include_all_parts,
        token_names=token_names,
        path_col=path_col,
    )

    # Feature grouping & assignment
    feature_to_idxs, paths = _build_feature_index(pl_work, path_col=path_col, how=how, parts=parts)
    feature_assignment = _assign_features(feature_to_idxs, ratios=ratios, seed=seed)
    mask = _mask_from_assignment(feature_to_idxs, feature_assignment, total=len(paths))
    tmp = pl_work.with_columns([pl.Series("_split", mask)])

    # Feature column for user convenience
    tmp = _add_feature_column(tmp, path_col=path_col, how=how, parts=parts)

    # Split
    train_df = tmp.filter(pl.col("_split") == "train").drop("_split")
    val_df = tmp.filter(pl.col("_split") == "val").drop("_split")
    test_df = tmp.filter(pl.col("_split") == "test").drop("_split")

    _maybe_log_ratio_drift(len(train_df), len(val_df), len(test_df), len(paths), ratios, verbose)

    # Return requested type
    if return_type == "polars" or return_type is None:
        return train_df, val_df, test_df

    if return_type == "filoma":
        # Lazy import filoma.DataFrame wrapper to avoid heavy imports at module import time
        try:
            from .dataframe import DataFrame as FDataFrame
        except Exception:
            from filoma.dataframe import DataFrame as FDataFrame

        return FDataFrame(train_df), FDataFrame(val_df), FDataFrame(test_df)

    if return_type == "pandas":
        try:
            return train_df.to_pandas(), val_df.to_pandas(), test_df.to_pandas()
        except Exception as e:
            raise RuntimeError(f"Failed to convert to pandas DataFrame: {e}")

    raise ValueError(f"Unknown return_type='{return_type}'")
