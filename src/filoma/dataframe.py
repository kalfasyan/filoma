"""DataFrame utilities for filoma.

Provides enhanced data manipulation capabilities for file and directory
analysis results using Polars.

Caching and pandas interop
--------------------------

This wrapper is Polars-first internally. Key pandas-related APIs:

- ``pandas``: returns a fresh pandas.DataFrame conversion of the current
    Polars DataFrame (no cache). Use this when you need an up-to-date pandas
    view after mutations.
- ``pandas_cached`` / ``to_pandas(force=False)``: returns a cached pandas
    conversion (created on first access). This is useful when repeated
    conversions would be expensive and the caller accepts an explicit cache.
- ``to_pandas(force=True)``: force a reconversion from Polars and update the cache.
- ``invalidate_pandas_cache()``: explicitly clear the cached pandas conversion.

Automatic invalidation
~~~~~~~~~~~~~~~~~~~~~~

To avoid returning stale cached pandas DataFrames after in-place mutations,
the wrapper automatically invalidates the cached pandas conversion in these
cases:

- Assigning columns via ``df[...] = ...`` (``__setitem__``)
- Common Polars in-place mutators detected by the delegated-call wrapper
    (Polars often returns ``None`` or the same DataFrame object for in-place
    operations). When such a return value is observed the cache is invalidated
    as a best-effort measure.

Callers who perform complex or external mutations should still call
``invalidate_pandas_cache()`` or ``to_pandas(force=True)`` to be certain the
cached view is refreshed.
"""

import datetime
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

import polars as pl
from loguru import logger
from rich.console import Console
from rich.table import Table

from filoma import dedup as _dedup

from .files.file_profiler import FileProfiler

# Note: filename-token discovery is implemented as the instance method
# `DataFrame.add_filename_features`. The standalone helper was intentionally
# removed to keep the API filoma-first and to avoid duplicate implementations.


try:
    import pandas as pd
except ImportError:
    pd = None

# Default DataFrame backend used by the `native` property. Can be 'polars' or 'pandas'.
# Change at runtime with `set_default_dataframe_backend()`.
DEFAULT_DF_BACKEND = "polars"

# Toggle: when True, methods on the underlying Polars DataFrame that return
# a Polars DataFrame will be wrapped back into filoma.DataFrame automatically.
# Defaults to False (Polars-first behavior).
DEFAULT_WRAP_POLARS = False


def set_default_wrap_polars(flag: bool) -> None:
    """Set whether delegated Polars-returning methods should be wrapped.

    When True, calls like `df.select(...)` will return a `filoma.DataFrame`.
    When False, they return native `polars.DataFrame` objects.
    """
    global DEFAULT_WRAP_POLARS
    DEFAULT_WRAP_POLARS = bool(flag)


def get_default_wrap_polars() -> bool:
    """Return current wrap-polars policy."""
    return DEFAULT_WRAP_POLARS


def set_default_dataframe_backend(backend: str) -> None:
    """Set the module default DataFrame backend used by DataFrame.native.

    backend must be one of: 'polars' or 'pandas'. If 'pandas' is selected but
    pandas is not installed, a RuntimeError is raised.
    """
    global DEFAULT_DF_BACKEND
    backend = backend.lower()
    if backend not in ("polars", "pandas"):
        raise ValueError("backend must be 'polars' or 'pandas'")
    if backend == "pandas" and pd is None:
        raise RuntimeError("pandas is not available in this environment")
    DEFAULT_DF_BACKEND = backend


def get_default_dataframe_backend() -> str:
    """Return the currently configured default dataframe backend."""
    return DEFAULT_DF_BACKEND


class DataFrame:
    """A wrapper around Polars DataFrame for enhanced file and directory analysis.

    This class provides a specialized interface for working with file path data,
    allowing for easy manipulation and analysis of filesystem information.

    All standard Polars DataFrame methods and properties are available through
    attribute delegation, so you can use this like a regular Polars DataFrame
    with additional file-specific functionality.
    """

    def __init__(
        self,
        data: Optional[Union[pl.DataFrame, List[str], List[Path], Dict[str, Any]]] = None,
        lineage: Optional[List[Dict[str, Any]]] = None,
    ):
        """Initialize a DataFrame.

        Args:
        ----
            data: Initial data. Can be:
                - A Polars DataFrame
                - A dictionary mapping column names to sequences (all same length)
                - A list of string paths
                - A list of Path objects
                - None for an empty DataFrame
            lineage: Optional list of lineage entries.

        """
        if data is None:
            self._df = pl.DataFrame({"path": []}, schema={"path": pl.String})
        elif isinstance(data, pl.DataFrame):
            self._df = data
        elif isinstance(data, dict):
            if not data:
                self._df = pl.DataFrame()
            else:
                processed: Dict[str, List[Any]] = {}
                expected_len: Optional[int] = None
                for col, values in data.items():
                    if not isinstance(values, (list, tuple)):
                        raise ValueError("Dictionary values must be list or tuple sequences")
                    seq = [str(x) if isinstance(x, Path) else x for x in values]
                    if expected_len is None:
                        expected_len = len(seq)
                    elif len(seq) != expected_len:
                        raise ValueError("All dictionary value sequences must have the same length")
                    processed[col] = seq
                self._df = pl.DataFrame(processed)
        elif isinstance(data, list):
            if data and isinstance(data[0], dict):
                # Handle list of dictionaries (from manifest or to_dicts())
                self._df = pl.from_dicts(data)
            else:
                paths = [str(path) for path in data]
                self._df = pl.DataFrame({"path": paths})
        else:
            raise ValueError("data must be a Polars DataFrame, dict of columns, list of paths, or None")
        self._pd_cache = None
        self.with_enrich = False
        self.with_filename_features = False
        self._lineage = lineage or []

    def _ensure_polars(self) -> pl.DataFrame:
        """Ensure the internal `_df` is a Polars DataFrame.

        If the underlying object is not a Polars DataFrame attempt to convert
        it (via pandas conversion if available or `pl.DataFrame(...)`). This
        prevents AttributeError when methods expect Polars APIs like
        `with_columns` or `map_elements`.
        """
        # Fast path
        if isinstance(self._df, pl.DataFrame):
            return self._df

        # Try pandas conversion first if pandas is present and this looks like
        # a pandas DataFrame
        try:
            if pd is not None and isinstance(self._df, pd.DataFrame):
                self._df = pl.from_pandas(self._df)
                # Invalidate any cached pandas view since we've converted
                self.invalidate_pandas_cache()
                return self._df
        except Exception:
            # fall through to generic conversion
            pass

        # Generic attempt to coerce into a Polars DataFrame
        try:
            self._df = pl.DataFrame(self._df)
            self.invalidate_pandas_cache()
            return self._df
        except Exception as exc:
            raise RuntimeError(f"Unable to coerce internal DataFrame to polars.DataFrame: {exc}")

    def __getattr__(self, name: str) -> Any:
        """Delegate attribute access to the underlying Polars DataFrame.

        This allows direct access to all Polars DataFrame methods and properties
        like columns, dtypes, shape, select, filter, group_by, etc.
        """
        # Directly return the attribute from the underlying Polars DataFrame.
        # NOTE: We intentionally do NOT wrap returned Polars DataFrames anymore.
        # This makes filoma.DataFrame behave like a Polars DataFrame by default
        # (calls like df.head(), df.select(...), etc. return native Polars
        # objects). This is a breaking change compared to previously wrapping
        # Polars results in filoma.DataFrame.
        try:
            attr = getattr(self._df, name)
        except AttributeError:
            # Preserve the original error semantics
            raise

        # If the attribute is callable, return a wrapper that conditionally
        # wraps returned polars.DataFrame objects into filoma.DataFrame
        if callable(attr):

            def wrapper(*args, **kwargs):
                result = attr(*args, **kwargs)
                # If the underlying call mutated the Polars DataFrame in-place,
                # Polars often returns None or the same object reference. In
                # that case invalidate the cached pandas conversion so future
                # .pandas/.pandas_cached calls reflect the mutation.
                if result is None or result is self._df:
                    try:
                        self.invalidate_pandas_cache()
                    except Exception:
                        # Best-effort: do not let cache invalidation break calls
                        pass
                    return result

                # If wrapping is enabled and result is a Polars DataFrame,
                # wrap it back into filoma.DataFrame for compatibility.
                # Propagate lineage to the new wrapper.
                if get_default_wrap_polars() and isinstance(result, pl.DataFrame):
                    return DataFrame(result, lineage=list(self._lineage))

                return result

            return wrapper

        # Non-callable attributes (properties) — if it's a Polars DataFrame and
        # wrapping is requested, wrap it; otherwise return as-is.
        if get_default_wrap_polars() and isinstance(attr, pl.DataFrame):
            return DataFrame(attr, lineage=list(self._lineage))

        return attr

    def __dir__(self) -> List[str]:
        """Expose both wrapper and underlying Polars attributes in interactive help."""
        attrs = set(super().__dir__())
        try:
            attrs.update(dir(self._df))
        except Exception:
            pass
        return sorted(list(attrs))

    def __getitem__(self, key):
        """Forward subscription (e.g., df['path']) to the underlying Polars DataFrame.

        Returns native Polars objects (Series or DataFrame) to match the default
        Polars-first behavior of this wrapper.
        """
        return self._df.__getitem__(key)

    def __setitem__(self, key, value):
        """Forward item assignment to the underlying Polars DataFrame."""
        # Polars DataFrame supports column assignment via df[key] = value
        # Try to support common user-friendly patterns: assigning a Python
        # sequence or a Series to create/replace a column. Polars' native
        # __setitem__ may raise TypeError in some versions, so handle that
        # explicitly and fall back to with_columns.
        try:
            if isinstance(key, str):
                # Accept polars Series, pandas Series, or Python sequences
                if isinstance(value, pl.Series):
                    series = value
                else:
                    try:
                        # pandas Series -> polars Series
                        if pd is not None and hasattr(value, "__array__") and not isinstance(value, (list, tuple)):
                            series = pl.Series(value)
                        elif isinstance(value, (list, tuple)):
                            series = pl.Series(key, list(value))
                        else:
                            # Scalar value: repeat across rows
                            series = pl.Series(key, [value] * len(self._df))
                    except Exception:
                        series = None

                if "series" in locals() and series is not None:
                    # Use with_columns to add/replace the column
                    self._df = self._df.with_columns(series.alias(key))
                    self.invalidate_pandas_cache()
                    return

            # Fallback to delegating to Polars __setitem__ for other patterns
            self._df.__setitem__(key, value)
            # Underlying data has changed; invalidate any cached pandas conversion
            self.invalidate_pandas_cache()
        except TypeError:
            # Polars raises TypeError for some unsupported assignment forms
            # (e.g., assigning a Series by index). Re-raise a clearer message
            msg = "DataFrame object does not support `Series` assignment by index\n\nUse `DataFrame.with_columns`."
            raise TypeError(msg)

    def invalidate_pandas_cache(self) -> None:
        """Clear the cached pandas conversion created by `to_pandas()`.

        Call this after mutating the underlying Polars DataFrame to ensure
        subsequent `pandas` accesses reflect the latest data.
        """
        self._pd_cache = None

    def add_lineage_entry(self, operation: str, **kwargs: Any) -> None:
        """Add a lineage entry to track the history of this DataFrame.

        Args:
        ----
            operation: Name of the operation performed.
            **kwargs: Parameters used for the operation.

        """
        self._lineage.append(
            {
                "operation": operation,
                "parameters": {k: str(v) if isinstance(v, Path) else v for k, v in kwargs.items()},
                "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        )

    @property
    def lineage(self) -> List[Dict[str, Any]]:
        """Return the lineage history of this DataFrame."""
        return self._lineage

    @property
    def df(self) -> pl.DataFrame:
        """Get the underlying Polars DataFrame."""
        return self._df

    def __len__(self) -> int:
        """Get the number of rows in the DataFrame."""
        # polars.DataFrame supports len(), but some wrapped/native objects
        # (for example older PyArrow-backed objects) may not implement __len__.
        # Try common fallbacks in order of preference.
        try:
            return len(self._df)
        except Exception:
            # polars exposes `.height` as row count and `.shape[0]` as rows
            try:
                return int(getattr(self._df, "height"))
            except Exception:
                try:
                    return int(self._df.shape[0])
                except Exception:
                    # Last resort: convert to pandas if available (cheap for small frames)
                    if pd is not None:
                        try:
                            return int(self._df.to_pandas().shape[0])
                        except Exception:
                            return 0
                    return 0

    def __repr__(self) -> str:
        """Return the string representation of the DataFrame."""
        # Avoid calling the underlying object's __str__/__repr__ if it may
        # raise TypeError (observed with some PyDataFrame wrappers). Use
        # safe fallbacks for a short textual preview.
        row_count = len(self)
        # Try polars' to_string-like rendering if available
        try:
            # Polars DataFrame implements __str__/__repr__; prefer repr()
            df_preview = repr(self._df)
        except Exception:
            try:
                # Try to convert to pandas for a safer repr
                if pd is not None:
                    df_preview = repr(self._df.to_pandas())
                else:
                    df_preview = "<unrepresentable DataFrame>"
            except Exception:
                df_preview = "<unrepresentable DataFrame>"

        return f"filoma.DataFrame with {row_count} rows\n{df_preview}"

    def __str__(self) -> str:
        """Return the string representation of the DataFrame."""
        return self.__repr__()

    def head(self, n: int = 5) -> "DataFrame":
        """Get the first n rows."""
        res = DataFrame(self._df.head(n), lineage=list(self._lineage))
        res.add_lineage_entry("head", n=n)
        return res

    def tail(self, n: int = 5) -> "DataFrame":
        """Get the last n rows."""
        res = DataFrame(self._df.tail(n), lineage=list(self._lineage))
        res.add_lineage_entry("tail", n=n)
        return res

    def add_path_components(self, inplace: bool = False) -> "DataFrame":
        """Add columns for path components (parent, name, stem, suffix).

        Returns
        -------
            New DataFrame with additional path component columns

        """
        cols_to_add = []
        if "parent" not in self._df.columns:
            cols_to_add.append(pl.col("path").map_elements(lambda x: str(Path(x).parent), return_dtype=pl.String).alias("parent"))
        if "name" not in self._df.columns:
            cols_to_add.append(pl.col("path").map_elements(lambda x: Path(x).name, return_dtype=pl.String).alias("name"))
        if "stem" not in self._df.columns:
            cols_to_add.append(pl.col("path").map_elements(lambda x: Path(x).stem, return_dtype=pl.String).alias("stem"))
        if "suffix" not in self._df.columns:
            cols_to_add.append(pl.col("path").map_elements(lambda x: Path(x).suffix, return_dtype=pl.String).alias("suffix"))

        if not cols_to_add:
            return self if inplace else DataFrame(self._df)

        df_with_components = self._df.with_columns(cols_to_add)
        if inplace:
            self._df = df_with_components
            self.invalidate_pandas_cache()
            self.add_lineage_entry("add_path_components")
            return self

        res = DataFrame(df_with_components, lineage=list(self._lineage))
        res.add_lineage_entry("add_path_components")
        return res

    def add_file_stats_cols(
        self,
        path: str = "path",
        base_path: Optional[Union[str, Path]] = None,
        compute_hash: bool = False,
        inplace: bool = False,
    ) -> "DataFrame":
        """Add file statistics columns (size, modified time, etc.) based on a column containing filesystem paths.

        Args:
        ----
            path: Name of the column containing file system paths.
            base_path: Optional base path. If provided, any non-absolute paths in the
                path column are resolved relative to this base.
            compute_hash: Whether to compute SHA256 hashes (slow for large files).
            inplace: If True, modify this DataFrame in-place and return ``self``.

        Returns:
        -------
            New DataFrame with file statistics columns added, or ``self`` when
            ``inplace=True``.

        Raises:
        ------
            ValueError: If the specified path column does not exist.

        """
        if path not in self._df.columns:
            raise ValueError(f"Column '{path}' not found in DataFrame")

        # Define the set of columns we intend to add
        target_cols = {
            "size_bytes",
            "modified_time",
            "created_time",
            "is_file",
            "is_dir",
            "owner",
            "group",
            "mode_str",
            "inode",
            "nlink",
            "sha256",
            "xattrs",
        }
        # Decide if we need to proceed. Proceed if any target column is missing,
        # OR if we need to compute hashes and the column is missing or has nulls.
        needs_hashes = compute_hash and ("sha256" not in self._df.columns or self._df["sha256"].null_count() > 0)
        missing_any = not all(c in self._df.columns for c in target_cols)

        if not missing_any and not needs_hashes:
            return self if inplace else DataFrame(self._df, lineage=list(self._lineage))

        # Resolve base path if provided
        base = Path(base_path) if base_path is not None else None

        # Use filoma's FileProfiler to collect rich file metadata
        profiler = FileProfiler()

        def get_file_stats(path_str: str) -> Dict[str, Any]:
            try:
                p = Path(path_str)
                if base is not None and not p.is_absolute():
                    p = base / p
                full_path = str(p)
                if not p.exists():
                    logger.warning(f"Path does not exist: {full_path}")
                    return {
                        "size_bytes": None,
                        "modified_time": None,
                        "created_time": None,
                        "is_file": None,
                        "is_dir": None,
                        "owner": None,
                        "group": None,
                        "mode_str": None,
                        "inode": None,
                        "nlink": None,
                        "sha256": None,
                        "xattrs": "{}",
                    }

                # Use the profiler; let it handle symlinks and permissions
                filo = profiler.probe(full_path, compute_hash=compute_hash)
                row = filo.as_dict()

                # Normalize keys to a stable schema used by this helper
                return {
                    "size_bytes": row.get("size"),
                    "modified_time": row.get("modified"),
                    "created_time": row.get("created"),
                    "is_file": row.get("is_file"),
                    "is_dir": row.get("is_dir"),
                    "owner": row.get("owner"),
                    "group": row.get("group"),
                    "mode_str": row.get("mode_str"),
                    "inode": row.get("inode"),
                    "nlink": row.get("nlink"),
                    "sha256": row.get("sha256"),
                    "xattrs": json.dumps(row.get("xattrs") or {}),
                }
            except Exception:
                # On any error, return a row of Nones/empties preserving schema
                return {
                    "size_bytes": None,
                    "modified_time": None,
                    "created_time": None,
                    "is_file": None,
                    "is_dir": None,
                    "owner": None,
                    "group": None,
                    "mode_str": None,
                    "inode": None,
                    "nlink": None,
                    "sha256": None,
                    "xattrs": "{}",
                }

        stats_data = [get_file_stats(p) for p in self._df[path].to_list()]

        stats_df = pl.DataFrame(
            stats_data,
            schema={
                "size_bytes": pl.Int64,
                "modified_time": pl.String,
                "created_time": pl.String,
                "is_file": pl.Boolean,
                "is_dir": pl.Boolean,
                "owner": pl.String,
                "group": pl.String,
                "mode_str": pl.String,
                "inode": pl.Int64,
                "nlink": pl.Int64,
                "sha256": pl.String,
                "xattrs": pl.String,
            },
        )

        # If columns already exist, we need to drop them before joining to avoid duplicates
        df_base = self._df
        overlapping_cols = [c for c in stats_df.columns if c in df_base.columns]
        if overlapping_cols:
            df_base = df_base.drop(overlapping_cols)

        df_with_stats = pl.concat([df_base, stats_df], how="horizontal")
        if inplace:
            self._df = df_with_stats
            self.invalidate_pandas_cache()
            self.add_lineage_entry("add_file_stats_cols", path_col=path, compute_hash=compute_hash)
            return self

        res = DataFrame(df_with_stats, lineage=list(self._lineage))
        res.add_lineage_entry("add_file_stats_cols", path_col=path, compute_hash=compute_hash)
        return res

    def add_duplicate_cols(self, hash_column: str = "sha256", compute_hash: bool = True) -> "DataFrame":
        """Flag exact duplicate rows by content hash.

        Groups rows by ``hash_column`` (default: ``sha256``) and marks every
        row that shares its hash with at least one other row as an exact
        duplicate. Rows with a missing/null hash (directories, or hashes
        that failed to compute) are never marked as duplicates.

        Args:
        ----
            hash_column: Column to group rows by. Defaults to "sha256".
            compute_hash: If True (default) and ``hash_column`` is missing,
                compute it first via ``add_file_stats_cols(compute_hash=True)``.
                Set to False to raise instead of silently computing hashes.

        Returns:
        -------
            New DataFrame with two additional columns:
            - ``is_exact_duplicate`` (bool): True if 2+ rows share the hash.
            - ``exact_dup_group_id`` (str | null): the shared hash for
              duplicate rows, null otherwise.

        Raises:
        ------
            ValueError: If ``hash_column`` is missing and ``compute_hash=False``.

        """
        base = self
        needs_recompute = hash_column not in base._df.columns or base._df[hash_column].null_count() > 0
        if needs_recompute:
            if hash_column != "sha256":
                raise ValueError(f"Column '{hash_column}' not found or contains nulls, and only 'sha256' can be auto-computed. Populate '{hash_column}' first.")
            if not compute_hash:
                raise ValueError("Column 'sha256' not found or contains nulls. Call add_file_stats_cols(compute_hash=True) first, or leave compute_hash=True.")
            base = base.add_file_stats_cols(compute_hash=True)

        counts = base._df.group_by(hash_column).len().rename({"len": "_dup_count"})
        joined = base._df.join(counts, on=hash_column, how="left")
        is_dup = pl.col(hash_column).is_not_null() & (pl.col("_dup_count") > 1)
        result = joined.with_columns(
            [
                is_dup.alias("is_exact_duplicate"),
                pl.when(is_dup).then(pl.col(hash_column)).otherwise(None).alias("exact_dup_group_id"),
            ]
        ).drop("_dup_count")

        res = DataFrame(result, lineage=list(base._lineage))
        res.add_lineage_entry("add_duplicate_cols", hash_column=hash_column)
        return res

    def add_corruption_cols(self) -> "DataFrame":
        """Flag corrupt or zero-byte files with a per-row integrity check.

        Runs the same checks as
        ``filoma.core.verifier.DatasetVerifier.check_integrity`` (zero-byte
        files, and unreadable/corrupt ``.jpg``/``.jpeg``/``.png``/``.bmp``
        images via Pillow), but attaches the result to each row instead of
        returning a separate aggregate report. Reuses the ``size_bytes``
        column when already present (from ``add_file_stats_cols``) to avoid
        a redundant ``stat()`` call per file.

        Returns
        -------
            New DataFrame with two additional columns:
            - ``is_corrupt`` (bool)
            - ``corruption_reason`` (str | null): "zero_byte",
              "corrupt_or_unsupported", or null when the file is fine.

        """
        from PIL import Image

        has_size = "size_bytes" in self._df.columns
        paths = self._df["path"].to_list()
        sizes = self._df["size_bytes"].to_list() if has_size else [None] * len(paths)
        image_suffixes = (".jpg", ".jpeg", ".png", ".bmp")

        def _check(path_str: str, known_size: Optional[int]) -> Optional[str]:
            try:
                p = Path(path_str)
                if not p.is_file():
                    return None
                size = known_size if known_size is not None else p.stat().st_size
                if size == 0:
                    return "zero_byte"
                if p.suffix.lower() in image_suffixes:
                    try:
                        with Image.open(p) as img:
                            img.verify()
                    except Exception:
                        return "corrupt_or_unsupported"
                return None
            except Exception:
                return None

        reasons = [_check(p, s) for p, s in zip(paths, sizes)]

        result = self._df.with_columns(
            [
                pl.Series("corruption_reason", reasons, dtype=pl.String),
                pl.Series("is_corrupt", [r is not None for r in reasons], dtype=pl.Boolean),
            ]
        )

        res = DataFrame(result, lineage=list(self._lineage))
        res.add_lineage_entry("add_corruption_cols")
        return res

    def add_embedding_cols(
        self,
        path: str = "path",
        base_path: Optional[Union[str, Path]] = None,
        max_chars: int = 4000,
        inplace: bool = False,
    ) -> "DataFrame":
        """Add a semantic ``embedding`` column computed from each file's content.

        Reuses the same embedding backend as filoma's RAG store
        (``filoma.core.rag``): Ollama's ``nomic-embed-text`` model if reachable
        on localhost, otherwise the ``sentence-transformers``
        ``all-MiniLM-L6-v2`` fallback. Only files recognized as text/code (see
        ``filoma.core.rag._is_text_file``) are embedded; the first
        ``max_chars`` characters of content are used to keep this fast on
        large files. Directories, binary files, and unreadable files
        (including images) get a null embedding — for images, use
        ``add_image_embedding_cols()`` instead.

        This turns "search files by meaning" (the RAG/``filoma ask`` feature)
        into a column on the file table itself, so relationships between
        files can be computed directly with plain DataFrame operations. Pair
        with ``add_semantic_similarity_cols()`` to surface each file's
        nearest neighbor by content.

        Args:
        ----
            path: Name of the column containing file system paths.
            base_path: Optional base path. Non-absolute paths in ``path`` are
                resolved relative to this base.
            max_chars: Number of leading characters read from each file
                before embedding. Keeps large files fast to embed.
            inplace: If True, modify this DataFrame in-place and return
                ``self``.

        Returns:
        -------
            New DataFrame with an ``embedding`` column (``list[float]`` or
            null per row), or ``self`` when ``inplace=True``.

        Raises:
        ------
            ValueError: If the specified path column does not exist.
            ImportError: If no embedding backend (Ollama or
                sentence-transformers) is available.

        """
        if path not in self._df.columns:
            raise ValueError(f"Column '{path}' not found in DataFrame")

        from .core.rag import _is_text_file, _resolve_embedder

        embedder = _resolve_embedder()
        base = Path(base_path) if base_path is not None else None

        texts: List[Optional[str]] = []
        for path_str in self._df[path].to_list():
            try:
                p = Path(path_str)
                if base is not None and not p.is_absolute():
                    p = base / p
                if not p.is_file() or not _is_text_file(p):
                    texts.append(None)
                    continue
                content = p.read_text(encoding="utf-8", errors="replace")[:max_chars]
                texts.append(content if content.strip() else None)
            except Exception:
                texts.append(None)

        # Embed only the non-null texts in a single batch call for efficiency.
        idx_to_embed = [i for i, t in enumerate(texts) if t is not None]
        vectors: List[Optional[List[float]]] = [None] * len(texts)
        if idx_to_embed:
            computed = embedder([texts[i] for i in idx_to_embed])
            for i, vec in zip(idx_to_embed, computed):
                vectors[i] = list(vec)

        result = self._df.with_columns(pl.Series("embedding", vectors, dtype=pl.List(pl.Float64)))

        if inplace:
            self._df = result
            self.invalidate_pandas_cache()
            self.add_lineage_entry("add_embedding_cols", path_col=path, max_chars=max_chars)
            return self

        res = DataFrame(result, lineage=list(self._lineage))
        res.add_lineage_entry("add_embedding_cols", path_col=path, max_chars=max_chars)
        return res

    def add_image_embedding_cols(
        self,
        path: str = "path",
        base_path: Optional[Union[str, Path]] = None,
        model: str = "clip-vit-b32",
        device: Optional[str] = None,
        inplace: bool = False,
    ) -> "DataFrame":
        """Add an ``image_embedding`` column computed from each row's image content.

        Reuses sentence-transformers' bundled CLIP support (already a core
        filoma dependency) to turn each image's pixels into a general-purpose
        visual-semantic feature vector — capturing subject/scene/composition,
        not just raw pixel or perceptual-hash similarity. Only files with a
        recognized image extension (see ``filoma.dedup.IMAGE_EXTS``) that
        Pillow can open are embedded; everything else (directories,
        non-images, unreadable/corrupt files) gets a null embedding
        automatically — there's no need to pre-filter the DataFrame to just
        images yourself. For text/code files, use ``add_embedding_cols()``
        instead.

        Pair with ``add_semantic_similarity_cols(embedding_col="image_embedding")``
        to build a similarity matrix / nearest-neighbor ranking over the
        images in the DataFrame — useful for spotting visual near-duplicates,
        clustering a dataset by visual content, or flagging an outlier image.

        Args:
        ----
            path: Name of the column containing file system paths.
            base_path: Optional base path. Non-absolute paths in ``path`` are
                resolved relative to this base.
            model: Which CLIP model to use — a short alias or any
                sentence-transformers image model id:

                - ``"clip-vit-b32"`` (default): fastest, 512-dim vectors.
                  Best choice for large batches / quick similarity checks.
                - ``"clip-vit-b16"``: sharper features, ~3-4x slower than
                  b32.
                - ``"clip-vit-l14"``: largest and slowest, most accurate.

                Models are cached per-process after first use, so repeated
                calls in the same session don't reload weights.
            device: Torch device to run on, e.g. ``"cpu"``, ``"cuda"``,
                ``"cuda:1"``, ``"mps"``. If None (default), a GPU is used
                automatically whenever one is available — sentence-transformers
                auto-selects CUDA, then Apple Silicon MPS, then CPU.
            inplace: If True, modify this DataFrame in-place and return
                ``self``.

        Returns:
        -------
            New DataFrame with an ``image_embedding`` column (``list[float]``
            or null per row), or ``self`` when ``inplace=True``.

        Raises:
        ------
            ValueError: If the specified path column does not exist, or the
                requested model fails to load.
            ImportError: If sentence-transformers is not installed.

        """
        if path not in self._df.columns:
            raise ValueError(f"Column '{path}' not found in DataFrame")

        from PIL import Image

        from filoma.dedup import is_image_path

        from .core.vision import _resolve_image_embedder

        embedder = _resolve_image_embedder(model, device=device)
        base = Path(base_path) if base_path is not None else None

        images: List[Any] = []
        row_indices: List[int] = []
        for i, path_str in enumerate(self._df[path].to_list()):
            try:
                p = Path(path_str)
                if base is not None and not p.is_absolute():
                    p = base / p
                if not p.is_file() or not is_image_path(str(p)):
                    continue
                img = Image.open(p).convert("RGB")
                images.append(img)
                row_indices.append(i)
            except Exception:
                continue

        # Embed only the images we could open, in a single batch call for efficiency.
        vectors: List[Optional[List[float]]] = [None] * len(self._df)
        if images:
            computed = embedder(images)
            for i, vec in zip(row_indices, computed):
                vectors[i] = list(vec)

        resolved_device = getattr(embedder, "device", device)
        result = self._df.with_columns(pl.Series("image_embedding", vectors, dtype=pl.List(pl.Float64)))

        if inplace:
            self._df = result
            self.invalidate_pandas_cache()
            self.add_lineage_entry("add_image_embedding_cols", path_col=path, model=model, device=resolved_device)
            return self

        res = DataFrame(result, lineage=list(self._lineage))
        res.add_lineage_entry("add_image_embedding_cols", path_col=path, model=model, device=resolved_device)
        return res

    def add_metadata_embedding_cols(
        self,
        columns: Optional[List[str]] = None,
        max_categories: int = 20,
        inplace: bool = False,
    ) -> "DataFrame":
        """Add a ``metadata_embedding`` column derived from structured file metadata.

        Complements ``add_embedding_cols()`` (which embeds file *content*)
        with a feature vector built from the DataFrame's own columns —
        things like size, depth, extension, owner, or timestamps. The result
        is an "uninterpretable" numeric fingerprint per row (normalized
        numeric features concatenated with one-hot categorical features),
        not meant to be read directly but to be combined with content
        embeddings in ``add_semantic_similarity_cols(metadata_embedding_col=...)``
        so that "similar files" can reflect shared metadata (same extension,
        similar size, same owner, close modification time) alongside shared
        meaning.

        Args:
        ----
            columns: Explicit list of DataFrame columns to build the feature
                vector from. If None (default), auto-selects from
                ``["size_bytes", "depth", "suffix", "owner", "group",
                "is_dir", "modified_time", "created_time"]`` — whichever of
                these are already present (e.g. via ``add_file_stats_cols()``,
                ``add_path_components()``, ``add_depth_col()``).
            max_categories: For categorical columns, the number of distinct
                values to one-hot encode individually; remaining values are
                lumped into a single "_other" bucket. Keeps the vector length
                bounded on high-cardinality columns (e.g. ``owner``).
            inplace: If True, modify this DataFrame in-place and return
                ``self``.

        Returns:
        -------
            New DataFrame with a ``metadata_embedding`` column
            (``list[float]`` per row), or ``self`` when ``inplace=True``.

        Raises:
        ------
            ValueError: If no usable columns are found (neither explicitly
                requested nor auto-detected).

        """
        default_numeric = ["size_bytes", "depth"]
        default_datetime = ["modified_time", "created_time"]
        default_categorical = ["suffix", "owner", "group", "is_dir"]

        if columns is not None:
            numeric_cols = [c for c in columns if c in default_numeric and c in self._df.columns]
            datetime_cols = [c for c in columns if c in default_datetime and c in self._df.columns]
            categorical_cols = [c for c in columns if c in default_categorical and c in self._df.columns]
            missing = [c for c in columns if c not in self._df.columns]
            if missing:
                raise ValueError(f"Column(s) not found in DataFrame: {missing}")
        else:
            numeric_cols = [c for c in default_numeric if c in self._df.columns]
            datetime_cols = [c for c in default_datetime if c in self._df.columns]
            categorical_cols = [c for c in default_categorical if c in self._df.columns]

        if not numeric_cols and not datetime_cols and not categorical_cols:
            raise ValueError(
                "No usable metadata columns found. Call add_file_stats_cols() "
                "(for size_bytes/owner/group/is_dir/modified_time/created_time), "
                "add_path_components() (for suffix), and/or add_depth_col() (for "
                "depth) first, or pass explicit `columns`."
            )

        n_rows = len(self._df)
        feature_columns: List[List[float]] = []  # each entry: one feature column's values across all rows

        def _minmax_normalize(values: List[Optional[float]]) -> List[float]:
            present = [v for v in values if v is not None]
            if not present:
                return [0.0] * len(values)
            lo, hi = min(present), max(present)
            if hi == lo:
                return [0.5 if v is not None else 0.0 for v in values]
            return [((v - lo) / (hi - lo)) if v is not None else 0.0 for v in values]

        for col in numeric_cols:
            raw = self._df[col].to_list()
            if col == "size_bytes":
                raw = [None if v is None else float(math.log1p(max(v, 0))) for v in raw]
            feature_columns.append(_minmax_normalize(raw))

        for col in datetime_cols:
            raw_strs = self._df[col].to_list()
            epochs: List[Optional[float]] = []
            for s in raw_strs:
                if not s:
                    epochs.append(None)
                    continue
                try:
                    epochs.append(datetime.datetime.fromisoformat(str(s)).timestamp())
                except (ValueError, TypeError):
                    epochs.append(None)
            feature_columns.append(_minmax_normalize(epochs))

        for col in categorical_cols:
            raw = self._df[col].to_list()
            str_vals = ["<null>" if v is None else str(v) for v in raw]
            counts: Dict[str, int] = {}
            for v in str_vals:
                counts[v] = counts.get(v, 0) + 1
            top_values = [v for v, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:max_categories]]
            top_set = set(top_values)
            categories = top_values + (["_other"] if any(v not in top_set for v in str_vals) else [])
            for cat in categories:
                feature_columns.append([1.0 if (v == cat or (cat == "_other" and v not in top_set)) else 0.0 for v in str_vals])

        vectors: List[List[float]] = [[col[i] for col in feature_columns] for i in range(n_rows)]

        result = self._df.with_columns(pl.Series("metadata_embedding", vectors, dtype=pl.List(pl.Float64)))

        used_columns = numeric_cols + datetime_cols + categorical_cols
        if inplace:
            self._df = result
            self.invalidate_pandas_cache()
            self.add_lineage_entry("add_metadata_embedding_cols", columns=used_columns)
            return self

        res = DataFrame(result, lineage=list(self._lineage))
        res.add_lineage_entry("add_metadata_embedding_cols", columns=used_columns)
        return res

    def add_semantic_similarity_cols(
        self,
        embedding_col: str = "embedding",
        top_k: int = 1,
        metadata_embedding_col: Optional[str] = None,
        content_weight: float = 0.6,
        inplace: bool = False,
    ) -> "DataFrame":
        """Add nearest-neighbor columns derived from cosine similarity of embeddings.

        Requires an embedding column (``list[float]`` per row), typically
        produced by ``add_embedding_cols()``. Computes pairwise cosine
        similarity between all rows with a non-null embedding and attaches,
        for each row, the path(s) and similarity score(s) of its ``top_k``
        closest other files — i.e. which files are semantically related,
        independent of folder location or filename.

        Optionally fuses this with a structured-metadata embedding (see
        ``add_metadata_embedding_cols()``): when ``metadata_embedding_col``
        is given, similarity between two rows becomes a weighted blend of
        their content-embedding cosine similarity and their
        metadata-embedding cosine similarity (``content_weight`` vs.
        ``1 - content_weight``) — so "similar files" can reflect shared
        metadata (extension, size, owner, timestamps) in addition to shared
        meaning. Rows missing a metadata embedding fall back to content-only
        similarity for pairs involving them.

        This is an O(n^2) computation over rows with embeddings, so it is
        best suited to per-folder or per-dataset analysis (hundreds to low
        thousands of files), not entire filesystems.

        Args:
        ----
            embedding_col: Column containing content embedding vectors.
                Defaults to "embedding" (from ``add_embedding_cols``). Pass
                ``"image_embedding"`` to build a similarity ranking over
                image content instead (from ``add_image_embedding_cols``).
            top_k: Number of nearest neighbors to attach per row.
            metadata_embedding_col: Optional column containing metadata
                embedding vectors (from ``add_metadata_embedding_cols``). If
                given, similarity is blended with content similarity.
            content_weight: Weight (0-1) given to content similarity when
                ``metadata_embedding_col`` is provided; the remainder
                (``1 - content_weight``) is given to metadata similarity.
                Ignored if ``metadata_embedding_col`` is None.
            inplace: If True, modify this DataFrame in-place and return
                ``self``.

        Returns:
        -------
            New DataFrame with two additional columns:
            - ``nearest_neighbor_paths`` (``list[str]`` | null): paths of the
              closest ``top_k`` other files, most similar first.
            - ``nearest_neighbor_similarities`` (``list[float]`` | null):
              matching similarity scores (higher = more similar).

        Raises:
        ------
            ValueError: If ``embedding_col`` (or ``metadata_embedding_col``,
                when given) is not found in the DataFrame.

        """
        if embedding_col not in self._df.columns:
            raise ValueError(f"Column '{embedding_col}' not found. Call add_embedding_cols() first.")
        if metadata_embedding_col is not None and metadata_embedding_col not in self._df.columns:
            raise ValueError(f"Column '{metadata_embedding_col}' not found. Call add_metadata_embedding_cols() first.")

        import numpy as np

        if "path" in self._df.columns:
            paths = [str(p) for p in self._df["path"].to_list()]
        else:
            paths = [str(i) for i in range(len(self._df))]
        raw_vectors = self._df[embedding_col].to_list()

        valid_idx = [i for i, v in enumerate(raw_vectors) if v is not None]
        neighbor_paths: List[Optional[List[str]]] = [None] * len(raw_vectors)
        neighbor_sims: List[Optional[List[float]]] = [None] * len(raw_vectors)

        def _cosine_sim_matrix(vecs: List[List[float]]) -> "np.ndarray":
            matrix = np.array(vecs, dtype=np.float64)
            norms = np.linalg.norm(matrix, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            normalized = matrix / norms
            return normalized @ normalized.T

        if len(valid_idx) > 1:
            sims = _cosine_sim_matrix([raw_vectors[i] for i in valid_idx])

            if metadata_embedding_col is not None:
                raw_meta = self._df[metadata_embedding_col].to_list()
                meta_for_valid = [raw_meta[i] for i in valid_idx]
                has_meta = np.array([v is not None for v in meta_for_valid])
                meta_matrix = [v if v is not None else [0.0] * len(next((m for m in meta_for_valid if m is not None), [0.0])) for v in meta_for_valid]
                meta_sims = _cosine_sim_matrix(meta_matrix)
                both_have_meta = np.outer(has_meta, has_meta)
                blended = content_weight * sims + (1 - content_weight) * meta_sims
                sims = np.where(both_have_meta, blended, sims)

            k = min(top_k, len(valid_idx) - 1)
            for row_pos, orig_i in enumerate(valid_idx):
                if k <= 0:
                    continue
                row_sims = sims[row_pos].copy()
                row_sims[row_pos] = -np.inf  # exclude self-similarity
                top_positions = np.argsort(row_sims)[::-1][:k]
                neighbor_paths[orig_i] = [paths[valid_idx[p]] for p in top_positions]
                neighbor_sims[orig_i] = [float(row_sims[p]) for p in top_positions]

        result = self._df.with_columns(
            [
                pl.Series("nearest_neighbor_paths", neighbor_paths, dtype=pl.List(pl.String)),
                pl.Series("nearest_neighbor_similarities", neighbor_sims, dtype=pl.List(pl.Float64)),
            ]
        )

        if inplace:
            self._df = result
            self.invalidate_pandas_cache()
            self.add_lineage_entry("add_semantic_similarity_cols", embedding_col=embedding_col, top_k=top_k, metadata_embedding_col=metadata_embedding_col, content_weight=content_weight)
            return self

        res = DataFrame(result, lineage=list(self._lineage))
        res.add_lineage_entry("add_semantic_similarity_cols", embedding_col=embedding_col, top_k=top_k, metadata_embedding_col=metadata_embedding_col, content_weight=content_weight)
        return res

    def add_depth_col(self, path: Optional[Union[str, Path]] = None, inplace: bool = False) -> "DataFrame":
        """Add a depth column showing the nesting level of each path.

        Args:
        ----
            path: The path to calculate depth from. If None, uses the common root.
            inplace: If True, modify this DataFrame in-place and return ``self``.

        Returns:
        -------
            New DataFrame with depth column

        """
        if "depth" in self._df.columns:
            return self if inplace else DataFrame(self._df)

        if path is None:
            # Find the common root path
            paths = [Path(p) for p in self._df["path"].to_list()]
            if not paths:
                path = Path()
            else:
                # Find common parent
                common_parts = []
                first_parts = paths[0].parts
                for i, part in enumerate(first_parts):
                    if all(len(p.parts) > i and p.parts[i] == part for p in paths):
                        common_parts.append(part)
                    else:
                        break
                path = Path(*common_parts) if common_parts else Path()
        else:
            path = Path(path)

        # Use a different local name to avoid shadowing the parameter inside calculate_depth
        path_root = path

        def calculate_depth(path_str: str) -> int:
            """Calculate the depth of a path relative to the provided root path."""
            try:
                p = Path(path_str)
                relative_path = p.relative_to(path_root)
                return len(relative_path.parts)
            except ValueError:
                # Path is not relative to the provided root path
                return len(Path(path_str).parts)

        df_with_depth = self._df.with_columns([pl.col("path").map_elements(calculate_depth, return_dtype=pl.Int64).alias("depth")])
        if inplace:
            self._df = df_with_depth
            self.invalidate_pandas_cache()
            self.add_lineage_entry("add_depth_col", reference_path=path)
            return self

        res = DataFrame(df_with_depth, lineage=list(self._lineage))
        res.add_lineage_entry("add_depth_col", reference_path=path)
        return res

    def filter_by_extension(self, extensions: Union[str, List[str]]) -> "DataFrame":
        """Filter the DataFrame to only include files with specific extensions.

        Args:
        ----
            extensions: File extension(s) to filter by (with or without leading dot)

        Returns:
        -------
            Filtered DataFrame

        """
        if isinstance(extensions, str):
            extensions = [extensions]

        # Normalize extensions (ensure they start with a dot)
        normalized_extensions = []
        for ext in extensions:
            if not ext.startswith("."):
                ext = "." + ext
            normalized_extensions.append(ext.lower())

        filtered_df = self._df.filter(
            pl.col("path").map_elements(
                lambda x: Path(x).suffix.lower() in normalized_extensions,
                return_dtype=pl.Boolean,
            )
        )
        res = DataFrame(filtered_df, lineage=list(self._lineage))
        res.add_lineage_entry("filter_by_extension", extensions=extensions)
        return res

    def filter_by_pattern(self, pattern: str) -> "DataFrame":
        """Filter the DataFrame by path pattern.

        Args:
        ----
            pattern: Pattern to match (uses Polars string contains)

        Returns:
        -------
            Filtered DataFrame

        """
        filtered_df = self._df.filter(pl.col("path").str.contains(pattern))
        res = DataFrame(filtered_df, lineage=list(self._lineage))
        res.add_lineage_entry("filter_by_pattern", pattern=pattern)
        return res

    def extension_counts(self) -> pl.DataFrame:
        """Group files by extension and count them.

        Returns
        -------
            Polars DataFrame with extension counts

        """
        # underlying `_df` is expected to be a Polars DataFrame
        df_with_ext = self._df.with_columns(
            [
                pl.col("path")
                .map_elements(
                    lambda x: (Path(x).suffix.lower() if Path(x).suffix else "<no extension>"),
                    return_dtype=pl.String,
                )
                .alias("extension")
            ]
        )
        result = df_with_ext.group_by("extension").len().sort("len", descending=True)
        return DataFrame(result)

    def directory_counts(self) -> pl.DataFrame:
        """Group files by their parent directory and count them.

        Returns
        -------
            Polars DataFrame with directory counts

        """
        # underlying `_df` is expected to be a Polars DataFrame
        df_with_parent = self._df.with_columns([pl.col("path").map_elements(lambda x: str(Path(x).parent), return_dtype=pl.String).alias("parent_dir")])
        result = df_with_parent.group_by("parent_dir").len().sort("len", descending=True)
        return DataFrame(result)

    def to_polars(self) -> pl.DataFrame:
        """Get the underlying Polars DataFrame."""
        return self._df

    def to_pandas(self, force: bool = False) -> Any:
        """Convert to a pandas DataFrame.

        By default this method will return a cached pandas conversion if one
        exists (for performance). Set ``force=True`` to reconvert from the
        current Polars DataFrame and update the cache.
        """
        if pd is None:
            raise ImportError("pandas is not installed. Please install it to use to_pandas().")
        # Convert and cache on first access or when forced
        if force or self._pd_cache is None:
            # Use Polars' to_pandas conversion for consistency
            self._pd_cache = self._df.to_pandas()
        return self._pd_cache

    @property
    def polars(self) -> pl.DataFrame:
        """Property access for the underlying Polars DataFrame (convenience)."""
        return self.to_polars()

    @property
    def pandas(self) -> Any:
        """Return a fresh pandas DataFrame conversion (not the cached object).

        This is intentionally a fresh conversion so callers who expect an
        up-to-date pandas view can access it directly. Use ``pandas_cached`` or
        ``to_pandas(force=False)`` to access the cached conversion for repeated
        reads, or ``to_pandas(force=True)`` to reconvert and update the cache.

        Raises
        ------
            ImportError: if pandas is not installed.

        """
        if pd is None:
            raise ImportError("pandas is not installed. Please install it to use pandas property.")
        return self._df.to_pandas()

    @property
    def pandas_cached(self) -> Any:
        """Return a cached pandas DataFrame, converting once if needed.

        This is useful when repeated conversions would be expensive and the
        caller is comfortable with an explicit cache that can be invalidated
        with ``invalidate_pandas_cache()`` or by calling ``to_pandas(force=True)``.
        """
        return self.to_pandas(force=False)

    @property
    def native(self):
        """Return the dataframe in the module-wide default backend.

        If `get_default_dataframe_backend()` is 'polars' this returns a Polars
        DataFrame, otherwise it returns a pandas DataFrame.
        """
        if get_default_dataframe_backend() == "polars":
            return self.polars
        return self.pandas

    @classmethod
    def from_pandas(cls, df: Any) -> "DataFrame":
        """Construct a filoma.DataFrame from a pandas DataFrame.

        This is a convenience wrapper that converts the pandas DataFrame into
        a Polars DataFrame and wraps it. Requires pandas to be installed.
        """
        if pd is None:
            raise RuntimeError("pandas is not available in this environment")
        # Convert via Polars for internal consistency
        pl_df = pl.from_pandas(df)
        return cls(pl_df)

    @classmethod
    def load(cls, path: Union[str, Path], format: Optional[str] = None) -> "DataFrame":
        """Load a DataFrame previously saved with ``save_csv()`` / ``save_parquet()`` (or ``write_json``).

        The counterpart to ``save_csv()``/``save_parquet()`` — lets a
        DataFrame built (and possibly enriched with embeddings, similarity
        columns, etc.) in one session be persisted to disk and picked back
        up later, without recomputing anything. Particularly useful for
        agent/MCP sessions, where the in-memory DataFrame only lives as long
        as that one connection: save once with ``save_parquet()`` (or the
        ``export_dataframe`` tool), then resume with ``load()`` (or the
        ``load_dataframe`` tool) in a fresh session instead of rebuilding
        from scratch.

        Args:
        ----
            path: Path to the file to load.
            format: ``"csv"``, ``"json"``, or ``"parquet"``. If None
                (default), inferred from the file extension.

        Returns:
        -------
            A new DataFrame wrapping the loaded data. Lineage starts fresh
            (recorded as a single ``"load"`` entry) since this isn't a
            transformation of an existing in-memory DataFrame.

        Raises:
        ------
            ValueError: If the file doesn't exist, or the format can't be
                inferred/is unsupported.

        """
        p = Path(path).expanduser()
        if not p.is_file():
            raise ValueError(f"File not found: {p}")

        resolved_format = (format or p.suffix.lstrip(".")).lower()
        if resolved_format in ("parquet", "pq"):
            pl_df = pl.read_parquet(p)
        elif resolved_format == "csv":
            pl_df = pl.read_csv(p)
        elif resolved_format == "json":
            pl_df = pl.read_json(p)
        else:
            raise ValueError(f"Unsupported format '{resolved_format}'. Use 'parquet', 'csv', or 'json' (or a matching file extension).")

        res = cls(pl_df)
        res.add_lineage_entry("load", path=str(p), format=resolved_format)
        return res

    def to_dict(self) -> Dict[str, List]:
        """Convert to a dictionary."""
        return self._df.to_dict(as_series=False)

    def save_csv(self, path: Union[str, Path]) -> None:
        """Save the DataFrame to CSV."""
        self._df.write_csv(str(path))

    def save_parquet(self, path: Union[str, Path]) -> None:
        """Save the DataFrame to Parquet format."""
        self._df.write_parquet(str(path))

    # Convenience methods for common Polars operations that users expect
    @property
    def columns(self) -> List[str]:
        """Get column names."""
        return self._df.columns

    @property
    def dtypes(self) -> List[pl.DataType]:
        """Get column data types."""
        return self._df.dtypes

    @property
    def shape(self) -> tuple:
        """Get DataFrame shape (rows, columns)."""
        # Attempt to return a (rows, cols) tuple even if the underlying
        # object doesn't expose .shape or len(). Use the same fallbacks as
        # in __len__ for rows and inspect columns for width.
        try:
            rows, cols = self._df.shape
            return (int(rows), int(cols))
        except Exception:
            # Rows fallback
            try:
                rows = len(self)
            except Exception:
                rows = 0
            # Columns fallback: try .columns or pandas conversion
            try:
                cols = len(getattr(self._df, "columns"))
            except Exception:
                try:
                    if pd is not None:
                        cols = self._df.to_pandas().shape[1]
                    else:
                        cols = 0
                except Exception:
                    cols = 0
            return (int(rows), int(cols))

    def describe(self, percentiles: Optional[List[float]] = None) -> pl.DataFrame:
        """Generate descriptive statistics.

        Args:
        ----
            percentiles: List of percentiles to include (default: [0.25, 0.5, 0.75])

        """
        # Polars' describe returns a new DataFrame summarizing columns; wrap it
        return DataFrame(self._df.describe(percentiles=percentiles))

    def info(self) -> None:
        """Print concise summary of the DataFrame."""
        print("filoma.DataFrame")
        print(f"Shape: {self.shape}")
        print(f"Columns: {len(self.columns)}")
        print()

        # Column info
        print("Column details:")
        for i, (col, dtype) in enumerate(zip(self.columns, self.dtypes)):
            null_count = self._df[col].null_count()
            print(f"  {i:2d}  {col:15s} {str(dtype):15s} {null_count:8d} nulls")

        # Memory usage approximation
        memory_mb = sum(self._df[col].estimated_size("mb") for col in self.columns)
        print(f"\nEstimated memory usage: {memory_mb:.2f} MB")

    def unique(self, subset: Optional[Union[str, List[str]]] = None) -> "DataFrame":
        """Get unique rows.

        Args:
        ----
            subset: Column name(s) to consider for uniqueness

        """
        if subset is None:
            result = self._df.unique()
        else:
            result = self._df.unique(subset=subset)
        res = DataFrame(result, lineage=list(self._lineage))
        res.add_lineage_entry("unique", subset=subset)
        return res

    def sort(self, by: Union[str, List[str]], descending: bool = False) -> "DataFrame":
        """Sort the DataFrame.

        Args:
        ----
            by: Column name(s) to sort by
            descending: Sort in descending order

        """
        result = self._df.sort(by, descending=descending)
        res = DataFrame(result, lineage=list(self._lineage))
        res.add_lineage_entry("sort", by=by, descending=descending)
        return res

    def enrich(self, inplace: bool = False):
        """Enrich the DataFrame by adding features like path components, file stats, and depth.

        Args:
        ----
            inplace: If True, perform the operation in-place and return self.
                     If False (default), return a new DataFrame with the changes.

        """
        # Chain the enrichment methods; this produces a new DataFrame wrapper.
        # These methods are now idempotent, so calling enrich() multiple times is safe.
        # Use intermediate wrappers to avoid redundant lineage entries if desired,
        # but here we'll just record a single 'enrich' operation for the user.
        # To avoid multiple inner lineage entries, we can use the underlying _df.
        enriched_df = self.add_path_components().add_file_stats_cols().add_depth_col()._df

        if inplace:
            # Update the internal state of the current object
            self._df = enriched_df
            self.with_enrich = True
            self.invalidate_pandas_cache()
            self.add_lineage_entry("enrich")
            return self

        # Return the new, enriched DataFrame instance
        res = DataFrame(enriched_df, lineage=list(self._lineage))
        res.with_enrich = True
        res.add_lineage_entry("enrich")
        return res

    def evaluate_duplicates(
        self,
        path_col: str = "path",
        text_threshold: float = 0.8,
        image_max_distance: int = 5,
        text_k: int = 3,
        show_table: bool = True,
        cross_dir_paths: Optional[List[str]] = None,
    ) -> dict:
        """Evaluate duplicates among files in the DataFrame.

        Scans the `path_col` column, runs exact, text and image duplicate
        detectors. Optionally filters to show only duplicates that cross
        directory boundaries (requires `cross_dir_paths` to define boundaries).
        """
        if path_col not in self._df.columns:
            raise ValueError(f"Column '{path_col}' not found in DataFrame")

        # filter for files only
        paths = [str(p) for p in self._df[path_col].to_list() if Path(p).is_file()]
        res = _dedup.find_duplicates(
            paths,
            text_k=text_k,
            text_threshold=text_threshold,
            image_max_distance=image_max_distance,
        )

        # Filter for cross-directory duplicates if requested
        if cross_dir_paths:
            for category in ["exact", "text", "image"]:
                filtered_groups = []
                for group in res.get(category, []):
                    # Check if file sources span multiple folders
                    source_dirs = set()
                    for p in group:
                        for cp in cross_dir_paths:
                            if str(p).startswith(str(cp)):
                                source_dirs.add(cp)
                    if len(source_dirs) > 1:
                        filtered_groups.append(group)
                res[category] = filtered_groups

        # Summarize counts
        exact_groups = res.get("exact", [])
        text_groups = res.get("text", [])
        image_groups = res.get("image", [])

        console = Console()
        if show_table:
            table = Table(title="Duplicate Summary (Cross-Dir)" if cross_dir_paths else "Duplicate Summary")
            table.add_column("Type", style="bold cyan")
            table.add_column("Groups", style="white")
            table.add_column("Files In Groups", style="white")
            table.add_row(
                "exact",
                str(len(exact_groups)),
                str(sum(len(g) for g in exact_groups) if exact_groups else 0),
            )
            table.add_row(
                "text",
                str(len(text_groups)),
                str(sum(len(g) for g in text_groups) if text_groups else 0),
            )
            table.add_row(
                "image",
                str(len(image_groups)),
                str(sum(len(g) for g in image_groups) if image_groups else 0),
            )
            console.print(table)

        logger.info(
            f"Duplicate summary: exact={len(exact_groups)} groups "
            f"({sum(len(g) for g in exact_groups) if exact_groups else 0} files), "
            f"text={len(text_groups)} groups "
            f"({sum(len(g) for g in text_groups) if text_groups else 0} files), "
            f"image={len(image_groups)} groups "
            f"({sum(len(g) for g in image_groups) if image_groups else 0} files)"
        )

        return res

    def add_filename_features(
        self,
        path_col: str = "path",
        sep: str = "_",
        prefix: Optional[str] = "feat",
        max_tokens: Optional[int] = None,
        include_parent: bool = False,
        include_all_parts: bool = False,
        token_names: Optional[Union[str, Sequence[str]]] = None,
        enrich: bool = False,
        inplace: bool = False,
    ) -> "DataFrame":
        """Discover filename features and add them as columns on this DataFrame.

        This instance method discovers separator-based tokens from filename
        stems and adds columns (e.g., `feat1`, `feat2` or `token1`, ...).

        Args:
        ----
            path_col: Column containing path strings to analyze (default: 'path').
            sep: Separator used to split filename stems (default: '_').
            prefix: Column name prefix for discovered tokens (default: 'feat').
            max_tokens: Optional cap on extracted tokens; by default uses observed max.
            include_parent: If True, add a `parent` column containing immediate parent folder name.
            include_all_parts: If True, add `path_part0`, `path_part1`, ... for all Path.parts.
            token_names: Optional list of token column names or 'auto' to generate readable names.
            enrich: If True, automatically enrich the DataFrame with path components and file stats before discovery.
            inplace: If True, perform the operation in-place and return self. Otherwise returns a new `filoma.DataFrame`.

        Returns:
        -------
            A new or modified `filoma.DataFrame` with discovered filename features.

        """
        # Determine the base Polars DataFrame for feature discovery
        base_df = self
        if enrich and not self.with_enrich:
            logger.info("Enriching DataFrame before discovering filename features")
            base_df = self.enrich(inplace=False)

        # Polars-native implementation inlined here (formerly a top-level helper).
        pl_df = base_df._df
        if path_col not in pl_df.columns:
            raise ValueError(f"DataFrame must have a '{path_col}' column")

        stems = [Path(s).stem for s in pl_df[path_col].to_list()]
        split_tokens = [stem.split(sep) if stem is not None else [""] for stem in stems]
        observed_max = max((len(t) for t in split_tokens), default=0)
        if max_tokens is None:
            eff_max = observed_max
        else:
            eff_max = max_tokens

        # Normalize token_names
        if token_names == "auto":
            token_names_seq = None
            auto_mode = True
        elif isinstance(token_names, (list, tuple)):
            token_names_seq = list(token_names)
            auto_mode = False
        else:
            token_names_seq = None
            auto_mode = False

        new_cols = []
        for i in range(eff_max):
            if token_names_seq is not None and i < len(token_names_seq) and token_names_seq[i]:
                col_name = token_names_seq[i]
            elif auto_mode:
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

        pl_result = pl_df.with_columns(new_cols)

        # Wrap the result in a filoma.DataFrame
        enriched_wrapper = DataFrame(pl_result, lineage=list(self._lineage))
        enriched_wrapper.with_filename_features = True
        enriched_wrapper.add_lineage_entry(
            "add_filename_features",
            sep=sep,
            prefix=prefix,
            max_tokens=max_tokens,
            include_parent=include_parent,
            token_names=token_names,
        )

        if inplace:
            self._df = enriched_wrapper._df
            self.with_filename_features = True
            if enrich and not self.with_enrich:
                self.with_enrich = True
            self.invalidate_pandas_cache()
            self._lineage = enriched_wrapper._lineage
            return self

        return enriched_wrapper
