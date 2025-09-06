import os
import tempfile
from pathlib import Path

import pytest

from filoma.directories import DirectoryProfiler

# Skip these filesystem-heavy tests on CI where external tools like `fd` may be missing
CI = os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true"
pytestmark = pytest.mark.skipif(CI, reason="Skip on CI where fd may be unavailable")


def test_rust_python_consistency():
    """Test that Rust and Python implementations produce consistent results."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # Create test structure
        # Root (depth 0)
        # ├── level1/ (depth 1)
        # │   ├── file1.txt (depth 2)
        # │   └── level2/ (depth 2)
        # │       ├── file2.txt (depth 3)
        # │       └── level3/ (depth 3)
        # │           └── file3.txt (depth 4)
        (tmp_path / "level1" / "level2" / "level3").mkdir(parents=True)
        (tmp_path / "level1" / "file1.txt").write_text("test")
        (tmp_path / "level1" / "level2" / "file2.txt").write_text("test")
        (tmp_path / "level1" / "level2" / "level3" / "file3.txt").write_text("test")

        # Test both implementations
        python_profiler = DirectoryProfiler(use_rust=False)
        rust_profiler = DirectoryProfiler(use_rust=True)

        # Test without max_depth - should find all files and folders
        result_py = python_profiler.probe(str(tmp_path))
        result_rust = rust_profiler.probe(str(tmp_path))

        # Expected: 3 files (file1.txt, file2.txt, file3.txt)
        # Expected: 4 folders (root, level1, level2, level3)
        assert result_py["summary"]["total_files"] == 3
        assert result_rust["summary"]["total_files"] == 3
        assert result_py["summary"]["total_folders"] == 4
        assert result_rust["summary"]["total_folders"] == 4

        assert result_py["summary"]["total_files"] == result_rust["summary"]["total_files"]
        assert result_py["summary"]["total_folders"] == result_rust["summary"]["total_folders"]

        # Test with max_depth=2
        # Rule: directories at depth <= 2, files at depth <= 3
        # Expected directories: root(0), level1(1), level2(2) = 3 folders
        # Expected files: file1.txt(2), file2.txt(3) = 2 files
        # Excluded: level3(3) directory, file3.txt(4) file
        result_py_depth = python_profiler.probe(str(tmp_path), max_depth=2)
        result_rust_depth = rust_profiler.probe(str(tmp_path), max_depth=2)

        assert result_py_depth["summary"]["total_files"] == 2
        assert result_rust_depth["summary"]["total_files"] == 2
        assert result_py_depth["summary"]["total_folders"] == 3
        assert result_rust_depth["summary"]["total_folders"] == 3
        assert result_py_depth["summary"]["max_depth"] == 2
        assert result_rust_depth["summary"]["max_depth"] == 2

        assert result_py_depth["summary"]["total_files"] == result_rust_depth["summary"]["total_files"]
        assert result_py_depth["summary"]["max_depth"] == result_rust_depth["summary"]["max_depth"]

        # Test with max_depth=1
        # Rule: directories at depth <= 1, files at depth <= 2
        # Expected directories: root(0), level1(1) = 2 folders
        # Expected files: file1.txt(2) = 1 file
        # Excluded: level2(2), level3(3) directories, file2.txt(3), file3.txt(4) files
        result_py_depth1 = python_profiler.probe(str(tmp_path), max_depth=1)
        result_rust_depth1 = rust_profiler.probe(str(tmp_path), max_depth=1)

        assert result_py_depth1["summary"]["total_files"] == 1
        assert result_rust_depth1["summary"]["total_files"] == 1
        assert result_py_depth1["summary"]["total_folders"] == 2
        assert result_rust_depth1["summary"]["total_folders"] == 2
        assert result_py_depth1["summary"]["max_depth"] == 1
        assert result_rust_depth1["summary"]["max_depth"] == 1

        assert result_py_depth1["summary"]["total_files"] == result_rust_depth1["summary"]["total_files"]
        assert result_py_depth1["summary"]["total_folders"] == result_rust_depth1["summary"]["total_folders"]


def test_empty_directory_consistency():
    """Test consistency with empty directories."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # Create structure with empty directories
        (tmp_path / "empty1").mkdir()
        (tmp_path / "non_empty").mkdir()
        (tmp_path / "non_empty" / "file.txt").write_text("test")
        (tmp_path / "non_empty" / "empty2").mkdir()

        python_profiler = DirectoryProfiler(use_rust=False)
        rust_profiler = DirectoryProfiler(use_rust=True)

        result_py = python_profiler.probe(str(tmp_path))
        result_rust = rust_profiler.probe(str(tmp_path))

        # Should have same counts
        assert result_py["summary"]["total_files"] == result_rust["summary"]["total_files"] == 1
        assert result_py["summary"]["total_folders"] == result_rust["summary"]["total_folders"] == 4  # root, empty1, non_empty, empty2


def test_single_file_consistency():
    """Test consistency with just a single file."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        (tmp_path / "single_file.txt").write_text("test")

        python_profiler = DirectoryProfiler(use_rust=False)
        rust_profiler = DirectoryProfiler(use_rust=True)

        result_py = python_profiler.probe(str(tmp_path))
        result_rust = rust_profiler.probe(str(tmp_path))

        assert result_py["summary"]["total_files"] == result_rust["summary"]["total_files"] == 1
        assert result_py["summary"]["total_folders"] == result_rust["summary"]["total_folders"] == 1  # just root
