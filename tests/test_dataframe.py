"""
Tests for the DataFrame functionality in DirectoryProfiler.
"""

import os
import sys
import tempfile
from pathlib import Path

# Add the src directory to the path (must happen before importing filoma modules)
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest

from filoma.dataframe import DataFrame
from filoma.directories.directory_profiler import DirectoryProfiler

# Skip tests on CI where external discovery tools (fd) are not available by default
CI = os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true"
pytestmark = pytest.mark.skipif(CI, reason="Skip on CI where fd may be unavailable")


class TestDataFrameFunctionality:
    """Test the DataFrame functionality."""

    def setup_method(self):
        """Set up test environment."""
        # Create a temporary directory with some test files
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)

        # Create some test files and directories
        (self.temp_path / "file1.txt").write_text("test content")
        (self.temp_path / "file2.py").write_text("print('hello')")
        (self.temp_path / "subdir").mkdir()
        (self.temp_path / "subdir" / "file3.md").write_text("# Test")
        (self.temp_path / "subdir" / "file4.json").write_text('{"test": true}')
        (self.temp_path / "empty_dir").mkdir()

    def teardown_method(self):
        """Clean up test environment."""
        import shutil

        shutil.rmtree(self.temp_dir)

    def test_dataframe_creation(self):
        """Test that DataFrame is created when enabled."""
        profiler = DirectoryProfiler(use_rust=False, build_dataframe=True)

        analysis = profiler.probe(self.temp_dir)
        df = profiler.get_dataframe(analysis)

        assert df is not None
        assert len(df) > 0
        assert "dataframe" in analysis

    def test_dataframe_disabled(self):
        """Test that DataFrame is not created when disabled."""
        profiler = DirectoryProfiler(use_rust=False, build_dataframe=False)

        analysis = profiler.probe(self.temp_dir)
        df = profiler.get_dataframe(analysis)

        assert df is None
        assert "dataframe" not in analysis

    def test_dataframe_availability_check(self):
        """Test dataframe availability checks."""
        profiler_enabled = DirectoryProfiler(build_dataframe=True)
        profiler_disabled = DirectoryProfiler(build_dataframe=False)

        # Note: Actual availability depends on polars installation
        # We just test the method exists and returns a boolean
        assert isinstance(profiler_enabled.is_dataframe_enabled(), bool)
        assert isinstance(profiler_disabled.is_dataframe_enabled(), bool)

    def test_polars_method_delegation(self):
        """Test that Polars methods are properly delegated."""
        # Create a simple DataFrame
        test_paths = ["/test/file1.txt", "/test/file2.py", "/test/subdir/file3.md"]
        df = DataFrame(test_paths)

        # Test property access
        assert hasattr(df, "columns")
        assert hasattr(df, "dtypes")
        assert hasattr(df, "shape")
        assert df.shape == (3, 1)
        assert "path" in df.columns

        # Test method delegation that should return filoma DataFrame
        selected = df.select("path")
        assert isinstance(selected, DataFrame)
        assert len(selected) == 3

        # Test filter method
        filtered = df.filter(df.df["path"].str.contains(".py"))
        assert isinstance(filtered, DataFrame)
        assert len(filtered) == 1

        # Test sort method
        sorted_df = df.sort("path")
        assert isinstance(sorted_df, DataFrame)
        assert len(sorted_df) == 3

    def test_enhanced_methods(self):
        """Test the enhanced convenience methods."""
        test_paths = ["/test/file1.txt", "/test/file2.py", "/test/subdir/file3.md"]
        df = DataFrame(test_paths)

        # Test info method
        df.info()  # Should not raise an exception

        # Test describe method
        desc = df.describe()
        assert desc is not None

        # Test unique method
        unique_df = df.unique()
        assert isinstance(unique_df, DataFrame)

        # Test with_columns (delegated method)
        df_with_length = df.with_columns([df.df["path"].str.len_chars().alias("path_length")])
        assert isinstance(df_with_length, DataFrame)
        assert "path_length" in df_with_length.columns

    def test_file_specific_methods_still_work(self):
        """Test that our original file-specific methods still work."""
        test_paths = ["/test/file1.txt", "/test/file2.py", "/test/file3.py", "/test/subdir/file4.md"]
        df = DataFrame(test_paths)

        # Test add_path_components
        df_with_components = df.add_path_components()
        assert isinstance(df_with_components, DataFrame)
        assert "parent" in df_with_components.columns
        assert "name" in df_with_components.columns
        assert "stem" in df_with_components.columns
        assert "suffix" in df_with_components.columns

        # Test filter_by_extension
        py_files = df.filter_by_extension(".py")
        assert isinstance(py_files, DataFrame)
        assert len(py_files) == 2

        # Test group_by_extension
        ext_counts = df.group_by_extension()
        assert ext_counts is not None
        assert len(ext_counts) > 0

        # Test group_by_directory
        dir_counts = df.group_by_directory()
        assert dir_counts is not None
        assert len(dir_counts) > 0


class TestStandaloneDataFrame:
    """Test the standalone DataFrame class."""

    def test_dataframe_creation_from_list(self):
        """Test creating DataFrame from list of paths."""
        paths = ["/path/to/file1.txt", "/path/to/file2.py"]
        df = DataFrame(paths)

        assert len(df) == 2
        assert "path" in df.df.columns

    def test_dataframe_creation_from_pathlib(self):
        """Test creating DataFrame from Path objects."""
        paths = [Path("/path/to/file1.txt"), Path("/path/to/file2.py")]
        df = DataFrame(paths)

        assert len(df) == 2
        assert "path" in df.df.columns

    def test_empty_dataframe(self):
        """Test creating empty DataFrame."""
        df = DataFrame()
        assert len(df) == 0
        assert "path" in df.df.columns

    def test_add_path_components(self):
        """Test adding path components."""
        paths = ["/home/user/file.txt", "/home/user/docs/readme.md"]
        df = DataFrame(paths)

        df_with_components = df.add_path_components()

        assert "parent" in df_with_components.df.columns
        assert "name" in df_with_components.df.columns
        assert "stem" in df_with_components.df.columns
        assert "suffix" in df_with_components.df.columns

    def test_filter_by_extension(self):
        """Test filtering by file extension."""
        paths = ["/path/to/file1.txt", "/path/to/file2.py", "/path/to/file3.py", "/path/to/file4.md"]
        df = DataFrame(paths)

        py_files = df.filter_by_extension(".py")
        assert len(py_files) == 2

        py_files2 = df.filter_by_extension("py")  # Without dot
        assert len(py_files2) == 2

        multiple_ext = df.filter_by_extension([".py", ".txt"])
        assert len(multiple_ext) == 3

    def test_filter_by_pattern(self):
        """Test filtering by pattern."""
        paths = ["/home/user/documents/file1.txt", "/home/user/projects/main.py", "/home/admin/config.json"]
        df = DataFrame(paths)

        user_files = df.filter_by_pattern("user")
        assert len(user_files) == 2

    def test_group_by_extension(self):
        """Test grouping by extension."""
        paths = [
            "/path/file1.txt",
            "/path/file2.txt",
            "/path/file3.py",
            "/path/file4",  # No extension
        ]
        df = DataFrame(paths)

        grouped = df.group_by_extension()
        assert len(grouped) >= 2  # At least .txt and <no extension>

    def test_group_by_directory(self):
        """Test grouping by directory."""
        paths = ["/home/user/file1.txt", "/home/user/file2.py", "/home/admin/config.json"]
        df = DataFrame(paths)

        grouped = df.group_by_directory()
        assert len(grouped) == 2  # Two different parent directories

    def test_add_depth_col(self):
        """Test adding depth column."""
        paths = ["/home/user/file.txt", "/home/user/docs/readme.md", "/home/user/docs/deep/nested/file.py"]
        df = DataFrame(paths)

        df_with_depth = df.add_depth_col("/home")
        assert "depth" in df_with_depth.df.columns

    def test_polars_method_delegation(self):
        """Test that Polars methods are properly delegated."""
        # Create a simple DataFrame
        test_paths = ["/test/file1.txt", "/test/file2.py", "/test/subdir/file3.md"]
        df = DataFrame(test_paths)

        # Test property access
        assert hasattr(df, "columns")
        assert hasattr(df, "dtypes")
        assert hasattr(df, "shape")
        assert df.shape == (3, 1)
        assert "path" in df.columns

        # Test method delegation that should return filoma DataFrame
        selected = df.select("path")
        assert isinstance(selected, DataFrame)
        assert len(selected) == 3

        # Test filter method
        filtered = df.filter(df.df["path"].str.contains(".py"))
        assert isinstance(filtered, DataFrame)
        assert len(filtered) == 1

        # Test sort method
        sorted_df = df.sort("path")
        assert isinstance(sorted_df, DataFrame)
        assert len(sorted_df) == 3

    def test_enhanced_methods(self):
        """Test the enhanced convenience methods."""
        test_paths = ["/test/file1.txt", "/test/file2.py", "/test/subdir/file3.md"]
        df = DataFrame(test_paths)

        # Test info method
        df.info()  # Should not raise an exception

        # Test describe method
        desc = df.describe()
        assert desc is not None

        # Test unique method
        unique_df = df.unique()
        assert isinstance(unique_df, DataFrame)

        # Test with_columns (delegated method)
        df_with_length = df.with_columns([df.df["path"].str.len_chars().alias("path_length")])
        assert isinstance(df_with_length, DataFrame)
        assert "path_length" in df_with_length.columns

    def test_file_specific_methods_still_work(self):
        """Test that our original file-specific methods still work."""
        test_paths = ["/test/file1.txt", "/test/file2.py", "/test/file3.py", "/test/subdir/file4.md"]
        df = DataFrame(test_paths)

        # Test add_path_components
        df_with_components = df.add_path_components()
        assert isinstance(df_with_components, DataFrame)
        assert "parent" in df_with_components.columns
        assert "name" in df_with_components.columns
        assert "stem" in df_with_components.columns
        assert "suffix" in df_with_components.columns

        # Test filter_by_extension
        py_files = df.filter_by_extension(".py")
        assert isinstance(py_files, DataFrame)
        assert len(py_files) == 2

        # Test group_by_extension
        ext_counts = df.group_by_extension()
        assert ext_counts is not None
        assert len(ext_counts) > 0

        # Test group_by_directory
        dir_counts = df.group_by_directory()
        assert dir_counts is not None
        assert len(dir_counts) > 0
