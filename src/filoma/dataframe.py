"""
DataFrame module for filoma - provides enhanced data manipulation capabilities
for file and directory analysis results using Polars.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import polars as pl


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
            self._df = pl.DataFrame({"path": []}, schema={"path": pl.String})
        elif isinstance(data, pl.DataFrame):
            if "path" not in data.columns:
                raise ValueError("DataFrame must contain a 'path' column")
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

        # If it's a method that returns a DataFrame, wrap it
        if callable(attr):
            def wrapper(*args, **kwargs):
                result = attr(*args, **kwargs)
                # If the result is a Polars DataFrame with a 'path' column, wrap it
                if isinstance(result, pl.DataFrame) and "path" in result.columns:
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
        df_with_components = self._df.with_columns([
            pl.col("path").map_elements(lambda x: str(Path(x).parent), return_dtype=pl.String).alias("parent"),
            pl.col("path").map_elements(lambda x: Path(x).name, return_dtype=pl.String).alias("name"),
            pl.col("path").map_elements(lambda x: Path(x).stem, return_dtype=pl.String).alias("stem"),
            pl.col("path").map_elements(lambda x: Path(x).suffix, return_dtype=pl.String).alias("suffix"),
        ])
        return DataFrame(df_with_components)

    def add_file_stats(self) -> "DataFrame":
        """
        Add file statistics columns (size, modified time, etc.).

        Returns:
            New DataFrame with file statistics columns
        """
        def get_file_stats(path_str: str) -> Dict[str, Any]:
            """Get file statistics for a given path."""
            try:
                path = Path(path_str)
                if path.exists() and path.is_file():
                    stat = path.stat()
                    return {
                        "size_bytes": stat.st_size,
                        "modified_time": stat.st_mtime,
                        "created_time": stat.st_ctime,
                        "is_file": True,
                        "is_dir": False,
                    }
                elif path.exists() and path.is_dir():
                    return {
                        "size_bytes": None,
                        "modified_time": None,
                        "created_time": None,
                        "is_file": False,
                        "is_dir": True,
                    }
                else:
                    return {
                        "size_bytes": None,
                        "modified_time": None,
                        "created_time": None,
                        "is_file": False,
                        "is_dir": False,
                    }
            except (OSError, IOError):
                return {
                    "size_bytes": None,
                    "modified_time": None,
                    "created_time": None,
                    "is_file": False,
                    "is_dir": False,
                }

        # Extract stats for each path
        stats_data = [get_file_stats(path) for path in self._df["path"].to_list()]

        # Create a DataFrame from the stats
        stats_df = pl.DataFrame(stats_data)

        # Concatenate with the original DataFrame
        df_with_stats = pl.concat([self._df, stats_df], how="horizontal")
        return DataFrame(df_with_stats)

    def add_depth_column(self, root_path: Optional[Union[str, Path]] = None) -> "DataFrame":
        """
        Add a depth column showing the nesting level of each path.

        Args:
            root_path: The root path to calculate depth from. If None, uses the common root.

        Returns:
            New DataFrame with depth column
        """
        if root_path is None:
            # Find the common root path
            paths = [Path(p) for p in self._df["path"].to_list()]
            if not paths:
                root_path = Path()
            else:
                # Find common parent
                common_parts = []
                first_parts = paths[0].parts
                for i, part in enumerate(first_parts):
                    if all(len(p.parts) > i and p.parts[i] == part for p in paths):
                        common_parts.append(part)
                    else:
                        break
                root_path = Path(*common_parts) if common_parts else Path()
        else:
            root_path = Path(root_path)

        def calculate_depth(path_str: str) -> int:
            """Calculate the depth of a path relative to root_path."""
            try:
                path = Path(path_str)
                relative_path = path.relative_to(root_path)
                return len(relative_path.parts) - 1 if relative_path.parts != ('.',) else 0
            except ValueError:
                # Path is not relative to root_path
                return len(Path(path_str).parts)

        df_with_depth = self._df.with_columns([
            pl.col("path").map_elements(calculate_depth, return_dtype=pl.Int64).alias("depth")
        ])
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
            if not ext.startswith('.'):
                ext = '.' + ext
            normalized_extensions.append(ext.lower())

        filtered_df = self._df.filter(
            pl.col("path").map_elements(
                lambda x: Path(x).suffix.lower() in normalized_extensions,
                return_dtype=pl.Boolean
            )
        )
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
        df_with_ext = self._df.with_columns([
            pl.col("path").map_elements(
                lambda x: Path(x).suffix.lower() if Path(x).suffix else "<no extension>",
                return_dtype=pl.String
            ).alias("extension")
        ])
        return df_with_ext.group_by("extension").len().sort("len", descending=True)

    def group_by_directory(self) -> pl.DataFrame:
        """
        Group files by their parent directory and count them.

        Returns:
            Polars DataFrame with directory counts
        """
        df_with_parent = self._df.with_columns([
            pl.col("path").map_elements(
                lambda x: str(Path(x).parent),
                return_dtype=pl.String
            ).alias("parent_dir")
        ])
        return df_with_parent.group_by("parent_dir").len().sort("len", descending=True)

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
