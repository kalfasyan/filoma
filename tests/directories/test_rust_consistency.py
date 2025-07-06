import tempfile
from pathlib import Path

from filoma.directories import DirectoryProfiler


def test_rust_python_consistency():
    """Test that Rust and Python implementations produce consistent results."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # Create test structure
        (tmp_path / "level1" / "level2" / "level3").mkdir(parents=True)
        (tmp_path / "level1" / "file1.txt").write_text("test")
        (tmp_path / "level1" / "level2" / "file2.txt").write_text("test")
        (tmp_path / "level1" / "level2" / "level3" / "file3.txt").write_text("test")

        # Test both implementations
        python_profiler = DirectoryProfiler(use_rust=False)
        rust_profiler = DirectoryProfiler(use_rust=True)

        # Test without max_depth
        result_py = python_profiler.analyze(str(tmp_path))
        result_rust = rust_profiler.analyze(str(tmp_path))

        assert result_py["summary"]["total_files"] == result_rust["summary"]["total_files"]
        assert result_py["summary"]["total_folders"] == result_rust["summary"]["total_folders"]

        # Test with max_depth=2
        result_py_depth = python_profiler.analyze(str(tmp_path), max_depth=2)
        result_rust_depth = rust_profiler.analyze(str(tmp_path), max_depth=2)

        assert result_py_depth["summary"]["total_files"] == result_rust_depth["summary"]["total_files"]
        assert result_py_depth["summary"]["max_depth"] == result_rust_depth["summary"]["max_depth"]

        # Should find exactly 2 files with max_depth=2
        assert result_py_depth["summary"]["total_files"] == 2
        assert result_rust_depth["summary"]["total_files"] == 2
