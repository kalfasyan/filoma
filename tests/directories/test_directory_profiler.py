"""Tests for DirectoryProfiler."""

import tempfile
from pathlib import Path

from filoma.directories import DirectoryProfiler


def test_directory_profiler_basic():
    """Test basic functionality of DirectoryProfiler."""
    # Create a temporary directory structure for testing
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # Create some test files and directories
        (tmp_path / "folder1").mkdir()
        (tmp_path / "folder2").mkdir()
        (tmp_path / "empty_folder").mkdir()
        (tmp_path / "nested" / "deep").mkdir(parents=True)

        # Create some files
        (tmp_path / "file1.txt").write_text("test content")
        (tmp_path / "file2.py").write_text("print('hello')")
        (tmp_path / "folder1" / "data.csv").write_text("col1,col2\n1,2")
        (tmp_path / "nested" / "image.png").write_text("fake png")

        # Test the profiler
        profiler = DirectoryProfiler()
        result = profiler.probe(str(tmp_path))

        # Verify results
        assert result["summary"]["total_files"] == 4
        assert result["summary"]["total_folders"] == 6  # including root
        assert result["summary"]["empty_folder_count"] == 3
        assert ".txt" in result["file_extensions"]
        assert ".py" in result["file_extensions"]
        assert "empty_folder" in [Path(p).name for p in result["empty_folders"]]


def test_directory_profiler_max_depth():
    """Test max_depth parameter."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # Create nested structure
        (tmp_path / "level1" / "level2" / "level3").mkdir(parents=True)
        (tmp_path / "level1" / "file1.txt").write_text("test")
        (tmp_path / "level1" / "level2" / "file2.txt").write_text("test")
        (tmp_path / "level1" / "level2" / "level3" / "file3.txt").write_text("test")

        profiler = DirectoryProfiler()

        # Test with max_depth=2
        result = profiler.probe(str(tmp_path), max_depth=2)

        # Should find files at level 1 and 2, but not level 3
        assert result["summary"]["total_files"] == 2
        assert result["summary"]["max_depth"] == 2


if __name__ == "__main__":
    test_directory_profiler_basic()
    test_directory_profiler_max_depth()
    print("✓ All tests passed!")
