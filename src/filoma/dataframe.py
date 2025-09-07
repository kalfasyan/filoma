"""
DataFrame module for filoma - provides enhanced data manipulation capabilities
for file and directory analysis results using Polars.
"""

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

import polars as pl
from loguru import logger

from .files.file_profiler import FileProfiler


class DataFrame:
    """
    A wrapper around Polars DataFrame for enhanced file and directory analysis.

    This class provides a specialized interface for working with file path data,
    allowing for easy manipulation and analysis of filesystem information.

    All standard Polars DataFrame methods and properties are available through
    attribute delegation, so you can use this like a regular Polars DataFrame
    with additional file-specific functionality.
    """

    def __init__(self, data: Optional[Union[pl.DataFrame, List[str], List[Path]]] = None):
        """
        Initialize a DataFrame.

        Args:
            data: Initial data. Can be:
                - A Polars DataFrame with a 'path' column
                - A list of string paths
                - A list of Path objects
                - None for an empty DataFrame
        """
        if data is None:
            # Default empty DataFrame with a path column for filesystem use-cases
            self._df = pl.DataFrame({"path": []}, schema={"path": pl.String})
        elif isinstance(data, pl.DataFrame):
            # Accept any Polars DataFrame schema. Some operations (path helpers)
            # expect a 'path' column, but group/aggregation helpers return
            # summary tables without 'path' and should still be wrapped.
            self._df = data
        elif isinstance(data, list):
            # Convert to string paths
            paths = [str(path) for path in data]
            self._df = pl.DataFrame({"path": paths})
        else:
            raise ValueError("data must be a Polars DataFrame, list of paths, or None")

    def __getattr__(self, name: str) -> Any:
        """
        Delegate attribute access to the underlying Polars DataFrame.

        This allows direct access to all Polars DataFrame methods and properties
        like columns, dtypes, shape, select, filter, group_by, etc.
        """
        attr = getattr(self._df, name)

        # If it's a method that returns a DataFrame, wrap Polars DataFrame
        if callable(attr):

            def wrapper(*args, **kwargs):
                result = attr(*args, **kwargs)
                # If the result is a Polars DataFrame, wrap it in filoma.DataFrame
                if isinstance(result, pl.DataFrame):
                    return DataFrame(result)
                # Otherwise return the result as-is
                return result

            return wrapper
        else:
            # For properties and non-callable attributes, return as-is
            return attr

    @property
    def df(self) -> pl.DataFrame:
        """Get the underlying Polars DataFrame."""
        return self._df

    def __len__(self) -> int:
        """Get the number of rows in the DataFrame."""
        return len(self._df)

    def __repr__(self) -> str:
        """String representation of the DataFrame."""
        return f"filoma.DataFrame with {len(self)} rows\n{self._df}"

    def __str__(self) -> str:
        """String representation of the DataFrame."""
        return self.__repr__()

    def head(self, n: int = 5) -> pl.DataFrame:
        """Get the first n rows."""
        return self._df.head(n)

    def tail(self, n: int = 5) -> pl.DataFrame:
        """Get the last n rows."""
        return self._df.tail(n)

    def add_path_components(self) -> "DataFrame":
        """
        Add columns for path components (parent, name, stem, suffix).

        Returns:
            New DataFrame with additional path component columns
        """
        df_with_components = self._df.with_columns(
            [
                pl.col("path").map_elements(lambda x: str(Path(x).parent), return_dtype=pl.String).alias("parent"),
                pl.col("path").map_elements(lambda x: Path(x).name, return_dtype=pl.String).alias("name"),
                pl.col("path").map_elements(lambda x: Path(x).stem, return_dtype=pl.String).alias("stem"),
                pl.col("path").map_elements(lambda x: Path(x).suffix, return_dtype=pl.String).alias("suffix"),
            ]
        )
        return DataFrame(df_with_components)

    def add_file_stats_cols(self, path: str = "path", base_path: Optional[Union[str, Path]] = None) -> "DataFrame":
        """
        Add file statistics columns (size, modified time, etc.) based on a column
        containing filesystem paths.

        Args:
            path: Name of the column containing file system paths.
            base_path: Optional base path. If provided, any non-absolute paths in the
                       path column are resolved relative to this base.

        Returns:
            New DataFrame with file statistics columns added.

        Raises:
            ValueError: If the specified path column does not exist.
        """
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
        return DataFrame(df_with_stats)

    def add_depth_col(self, path: Optional[Union[str, Path]] = None) -> "DataFrame":
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

        df_with_depth = self._df.with_columns([pl.col("path").map_elements(calculate_depth, return_dtype=pl.Int64).alias("depth")])
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
        filtered_df = self._df.filter(pl.col("path").str.contains(pattern))
        return DataFrame(filtered_df)

    def group_by_extension(self) -> pl.DataFrame:
        """
        Group files by extension and count them.

        Returns:
            Polars DataFrame with extension counts
        """
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
        df_with_parent = self._df.with_columns(
            [pl.col("path").map_elements(lambda x: str(Path(x).parent), return_dtype=pl.String).alias("parent_dir")]
        )
        result = df_with_parent.group_by("parent_dir").len().sort("len", descending=True)
        return DataFrame(result)

    def to_polars(self) -> pl.DataFrame:
        """Get the underlying Polars DataFrame."""
        return self._df

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
        return self._df.shape

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
    def auto_split(
        self,
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
        return_type: str = "filoma",
    ):
        """Deterministically split this filoma DataFrame into train/val/test.

        This is a thin wrapper around ``filoma.ml.auto_split`` so you can call
        ``df.auto_split(...)`` directly on a filoma DataFrame instance.

        Args mirror :func:`filoma.ml.auto_split` except ``df`` is implicit.

        By default ``return_type='filoma'`` so the three returned objects are
        filoma.DataFrame wrappers.
        """
        # Local import to avoid loading ml utilities unless used
        from . import ml  # type: ignore

        return ml.auto_split(
            self,
            train_val_test=train_val_test,
            how=how,
            parts=parts,
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
