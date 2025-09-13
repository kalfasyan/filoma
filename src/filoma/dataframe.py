"""
DataFrame module for filoma - provides enhanced data manipulation capabilities
for file and directory analysis results using Polars.

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

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

import polars as pl
from loguru import logger
from rich.console import Console
from rich.table import Table

from filoma import dedup as _dedup

from .files.file_profiler import FileProfiler

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
    """
    A wrapper around Polars DataFrame for enhanced file and directory analysis.

    This class provides a specialized interface for working with file path data,
    allowing for easy manipulation and analysis of filesystem information.

    All standard Polars DataFrame methods and properties are available through
    attribute delegation, so you can use this like a regular Polars DataFrame
    with additional file-specific functionality.
    """

    def __init__(self, data: Optional[Union[pl.DataFrame, List[str], List[Path], Dict[str, Any]]] = None):
        """
        Initialize a DataFrame.

        Args:
            data: Initial data. Can be:
                - A Polars DataFrame
                - A dictionary mapping column names to sequences (all same length)
                - A list of string paths
                - A list of Path objects
                - None for an empty DataFrame
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
            paths = [str(path) for path in data]
            self._df = pl.DataFrame({"path": paths})
        else:
            raise ValueError("data must be a Polars DataFrame, dict of columns, list of paths, or None")
        self._pd_cache = None
        self.with_enrich = False
        self.with_filename_features = False

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
        """
        Delegate attribute access to the underlying Polars DataFrame.

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
                if get_default_wrap_polars() and isinstance(result, pl.DataFrame):
                    return DataFrame(result)

                return result

            return wrapper

        # Non-callable attributes (properties) — if it's a Polars DataFrame and
        # wrapping is requested, wrap it; otherwise return as-is.
        if get_default_wrap_polars() and isinstance(attr, pl.DataFrame):
            return DataFrame(attr)

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
        self._ensure_polars()
        return self._df.__getitem__(key)

    def __setitem__(self, key, value):
        """Forward item assignment to the underlying Polars DataFrame."""
        # Polars DataFrame supports column assignment via df[key] = value
        self._ensure_polars()
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
        """String representation of the DataFrame."""
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
        """String representation of the DataFrame."""
        return self.__repr__()

    def head(self, n: int = 5) -> pl.DataFrame:
        """Get the first n rows."""
        self._ensure_polars()
        return self._df.head(n)

    def tail(self, n: int = 5) -> pl.DataFrame:
        """Get the last n rows."""

        self._ensure_polars()
        return self._df.tail(n)

    def add_path_components(self, inplace: bool = False) -> "DataFrame":
        """
        Add columns for path components (parent, name, stem, suffix).

        Returns:
            New DataFrame with additional path component columns
        """
        self._ensure_polars()
        df_with_components = self._df.with_columns(
            [
                pl.col("path").map_elements(lambda x: str(Path(x).parent), return_dtype=pl.String).alias("parent"),
                pl.col("path").map_elements(lambda x: Path(x).name, return_dtype=pl.String).alias("name"),
                pl.col("path").map_elements(lambda x: Path(x).stem, return_dtype=pl.String).alias("stem"),
                pl.col("path").map_elements(lambda x: Path(x).suffix, return_dtype=pl.String).alias("suffix"),
            ]
        )
        if inplace:
            self._df = df_with_components
            self.invalidate_pandas_cache()
            return self

        return DataFrame(df_with_components)

    def add_file_stats_cols(self, path: str = "path", base_path: Optional[Union[str, Path]] = None, inplace: bool = False) -> "DataFrame":
        """
        Add file statistics columns (size, modified time, etc.) based on a column
        containing filesystem paths.

        Args:
            path: Name of the column containing file system paths.
            base_path: Optional base path. If provided, any non-absolute paths in the
                       path column are resolved relative to this base.

        Returns:
            New DataFrame with file statistics columns added, or ``self`` when ``inplace=True``.

        Raises:
            ValueError: If the specified path column does not exist.
        """
        self._ensure_polars()

        if path not in self._df.columns:
            raise ValueError(f"Column '{path}' not found in DataFrame")

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
                filo = profiler.probe(full_path, compute_hash=False)
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

        df_with_stats = pl.concat([self._df, stats_df], how="horizontal")
        if inplace:
            self._df = df_with_stats
            self.invalidate_pandas_cache()
            return self

        return DataFrame(df_with_stats)

    def add_depth_col(self, path: Optional[Union[str, Path]] = None, inplace: bool = False) -> "DataFrame":
        """
        Add a depth column showing the nesting level of each path.

        Args:
            path: The path to calculate depth from. If None, uses the common root.

        Returns:
            New DataFrame with depth column
        """
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

        self._ensure_polars()
        df_with_depth = self._df.with_columns([pl.col("path").map_elements(calculate_depth, return_dtype=pl.Int64).alias("depth")])
        if inplace:
            self._df = df_with_depth
            self.invalidate_pandas_cache()
            return self

        return DataFrame(df_with_depth)

    def filter_by_extension(self, extensions: Union[str, List[str]]) -> "DataFrame":
        """
        Filter the DataFrame to only include files with specific extensions.

        Args:
            extensions: File extension(s) to filter by (with or without leading dot)

        Returns:
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

        # Ensure we have a Polars DataFrame to operate on
        self._ensure_polars()
        filtered_df = self._df.filter(pl.col("path").map_elements(lambda x: Path(x).suffix.lower() in normalized_extensions, return_dtype=pl.Boolean))
        return DataFrame(filtered_df)

    def filter_by_pattern(self, pattern: str) -> "DataFrame":
        """
        Filter the DataFrame by path pattern.

        Args:
            pattern: Pattern to match (uses Polars string contains)

        Returns:
            Filtered DataFrame
        """

        self._ensure_polars()
        filtered_df = self._df.filter(pl.col("path").str.contains(pattern))
        return DataFrame(filtered_df)

    def group_by_extension(self) -> pl.DataFrame:
        """
        Group files by extension and count them.

        Returns:
            Polars DataFrame with extension counts
        """
        self._ensure_polars()
        df_with_ext = self._df.with_columns(
            [
                pl.col("path")
                .map_elements(lambda x: Path(x).suffix.lower() if Path(x).suffix else "<no extension>", return_dtype=pl.String)
                .alias("extension")
            ]
        )
        result = df_with_ext.group_by("extension").len().sort("len", descending=True)
        return DataFrame(result)

    def group_by_directory(self) -> pl.DataFrame:
        """
        Group files by their parent directory and count them.

        Returns:
            Polars DataFrame with directory counts
        """
        self._ensure_polars()
        df_with_parent = self._df.with_columns(
            [pl.col("path").map_elements(lambda x: str(Path(x).parent), return_dtype=pl.String).alias("parent_dir")]
        )
        result = df_with_parent.group_by("parent_dir").len().sort("len", descending=True)
        return DataFrame(result)

    def to_polars(self) -> pl.DataFrame:
        """Get the underlying Polars DataFrame."""

        # Ensure we return a Polars DataFrame
        return self._ensure_polars()

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

        Raises:
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
        """
        Generate descriptive statistics.

        Args:
            percentiles: List of percentiles to include (default: [0.25, 0.5, 0.75])
        """
        return self._df.describe(percentiles=percentiles)

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
        """
        Get unique rows.

        Args:
            subset: Column name(s) to consider for uniqueness
        """
        if subset is None:
            result = self._df.unique()
        else:
            result = self._df.unique(subset=subset)
        return DataFrame(result)

    def sort(self, by: Union[str, List[str]], descending: bool = False) -> "DataFrame":
        """
        Sort the DataFrame.

        Args:
            by: Column name(s) to sort by
            descending: Sort in descending order
        """
        result = self._df.sort(by, descending=descending)
        return DataFrame(result)

    # -------------------- ML convenience API -------------------- #
    def split_data(
        self,
        train_val_test: Tuple[float, float, float] = (80, 10, 10),
        feature: Union[str, Sequence[str]] = "path_parts",
        path_parts: Optional[Iterable[int]] = (-1,),
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
        return_type: str = "filoma",
    ):
        """Deterministically split this filoma DataFrame into train/val/test.

        This is a thin wrapper around ``filoma.ml.split_data`` so you can call
        ``df.split_data(...)`` directly on a filoma DataFrame instance.

        Args mirror :func:`filoma.ml.split_data` except ``df`` is implicit.

        By default ``return_type='filoma'`` so the three returned objects are
        filoma.DataFrame wrappers.
        """
        # Local import to avoid loading ml utilities unless used
        from . import ml  # type: ignore

        return ml.split_data(
            self,
            train_val_test=train_val_test,
            feature=feature,
            path_parts=path_parts,
            seed=seed,
            discover=discover,
            sep=sep,
            feat_prefix=feat_prefix,
            max_tokens=max_tokens,
            include_parent=include_parent,
            include_all_parts=include_all_parts,
            token_names=token_names,
            path_col=path_col,
            verbose=verbose,
            return_type=return_type,
        )

    def enrich(self, inplace: bool = False):
        """
        Enrich the DataFrame by adding features like path components, file stats, and depth.

        Args:
            inplace: If True, perform the operation in-place and return self.
                     If False (default), return a new DataFrame with the changes.
        """
        # Chain the enrichment methods; this produces a new DataFrame wrapper
        enriched_wrapper = self.add_path_components().add_file_stats_cols().add_depth_col()
        enriched_wrapper.with_enrich = True

        if inplace:
            # Update the internal state of the current object
            self._df = enriched_wrapper._df
            self.with_enrich = True
            self.invalidate_pandas_cache()
            return self

        # Return the new, enriched DataFrame instance
        return enriched_wrapper

    def evaluate_duplicates(
        self,
        path_col: str = "path",
        text_threshold: float = 0.8,
        image_max_distance: int = 5,
        text_k: int = 3,
        show_table: bool = True,
    ) -> dict:
        """Evaluate duplicates among files in the DataFrame.

        Scans the `path_col` column, runs exact, text and image duplicate
        detectors and prints a small Rich table summarizing counts.

        Returns the raw dict produced by `filoma.dedup.find_duplicates`.
        """
        self._ensure_polars()
        if path_col not in self._df.columns:
            raise ValueError(f"Column '{path_col}' not found in DataFrame")

        paths = [str(p) for p in self._df[path_col].to_list()]
        res = _dedup.find_duplicates(paths, text_k=text_k, text_threshold=text_threshold, image_max_distance=image_max_distance)

        # Summarize counts
        exact_groups = res.get("exact", [])
        text_groups = res.get("text", [])
        image_groups = res.get("image", [])

        console = Console()
        if show_table:
            table = Table(title="Duplicate Summary")
            table.add_column("Type", style="bold cyan")
            table.add_column("Groups", style="white")
            table.add_column("Files In Groups", style="white")
            table.add_row("exact", str(len(exact_groups)), str(sum(len(g) for g in exact_groups) if exact_groups else 0))
            table.add_row("text", str(len(text_groups)), str(sum(len(g) for g in text_groups) if text_groups else 0))
            table.add_row("image", str(len(image_groups)), str(sum(len(g) for g in image_groups) if image_groups else 0))
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

    def add_filename_features(self, enrich: bool = False, inplace: bool = False, **kwargs) -> "DataFrame":
        """
        Discover filename features using filoma.ml.add_filename_features.

        This is a thin wrapper around ``filoma.ml.add_filename_features``
        so you can call ``df.add_filename_features(...)`` directly on a
        filoma DataFrame instance.

        Args:
            enrich: If True, automatically enrich the DataFrame with path components
                    and file stats before discovering filename features.
            inplace: If True, perform the operation in-place and return self.
                     If False (default), return a new DataFrame with the changes.
            kwargs: Additional keyword arguments passed to
                ``filoma.ml.add_filename_features``.

        Returns:
            A new or modified filoma.DataFrame with discovered filename features.
        """
        from . import ml  # type: ignore

        # Determine the base DataFrame for feature discovery
        base_df = self
        if enrich and not self.with_enrich:
            logger.info("Enriching DataFrame before discovering filename features")
            # Create an enriched version to work from, respecting inplace for the final result
            base_df = self.enrich(inplace=False)

        # The ML helper returns a new filoma.DataFrame wrapper
        result_df = ml.add_filename_features(base_df, **kwargs)

        # The result could be a filoma.DataFrame or a raw polars/other frame
        if not isinstance(result_df, DataFrame):
            enriched_wrapper = DataFrame(result_df)
        else:
            enriched_wrapper = result_df

        enriched_wrapper.with_filename_features = True

        if inplace:
            # Update the internal state of the current object
            self._df = enriched_wrapper._df
            self.with_filename_features = True
            # If enrichment also happened, mark it
            if enrich and not self.with_enrich:
                self.with_enrich = True
            self.invalidate_pandas_cache()
            return self

        # Return the new, enriched DataFrame instance
        return enriched_wrapper
