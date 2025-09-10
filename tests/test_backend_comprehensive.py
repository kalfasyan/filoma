#!/usr/bin/env python3
"""
Comprehensive backend testing for filoma.

This test suite validates all three backends (Python, Rust, fd) across different scenarios
to ensure they work correctly and provide consistent results where expected.
"""

import tempfile
import time
from pathlib import Path

import pytest

from filoma.core import FdIntegration
from filoma.directories import DirectoryProfiler, DirectoryProfilerConfig, FdFinder


class TestBackendComprehensive:
    """Comprehensive backend testing suite."""

    @pytest.fixture
    def test_directory(self):
        """Create a complex test directory structure."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            dirs = [
                "docs",
                "docs/images",
                "src",
                "src/modules",
                "tests",
                "empty_dir",
                "data",
                ".hidden",
            ]
            for dir_name in dirs:
                (tmp_path / dir_name).mkdir(parents=True, exist_ok=True)

            files = {
                "docs/README.md": "# Project\nThis is a test project.",
                "docs/guide.txt": "User guide content here.",
                "docs/images/logo.png": "fake png data" * 10,
                "docs/images/diagram.jpg": "fake jpg data" * 20,
                "src/main.py": "def main():\n    print('hello')\n\nif __name__ == '__main__':\n    main()",
                "src/utils.py": "def helper():\n    return True",
                "src/modules/__init__.py": "",
                "src/modules/core.py": "class Core:\n    pass",
                "src/modules/helpers.rs": "fn helper() -> bool { true }",
                "tests/test_main.py": "def test_main():\n    assert True",
                "tests/test_utils.py": "def test_helper():\n    assert True",
                "data/large_file.txt": "x" * 1000,
                "data/small.json": '{"key": "value"}',
                ".hidden/secret.txt": "secret content",
            }

            for file_path, content in files.items():
                (tmp_path / file_path).write_text(content)

            yield str(tmp_path)

    def test_python_backend_basic(self, test_directory):
        """Test Python backend basic functionality."""

        profiler_cfg = DirectoryProfilerConfig(search_backend="python", show_progress=False)
        profiler = DirectoryProfiler(profiler_cfg)
        result = profiler.probe(test_directory)

        # Verify basic counts
        assert result["summary"]["total_files"] >= 12
        assert result["summary"]["total_folders"] >= 8
        assert result["summary"]["empty_folder_count"] >= 1

        # Verify extensions are detected
        extensions = result["file_extensions"]
        assert ".py" in extensions
        assert ".md" in extensions
        assert ".txt" in extensions
        assert ".rs" in extensions

        # Verify empty folders are detected
        empty_folders = [Path(p).name for p in result["empty_folders"]]
        assert "empty_dir" in empty_folders

    def test_rust_backend_basic(self, test_directory):
        """Test Rust backend basic functionality."""
        profiler_cfg = DirectoryProfilerConfig(search_backend="rust", show_progress=False)
        profiler = DirectoryProfiler(profiler_cfg)
        result = profiler.probe(test_directory)

        assert result["summary"]["total_files"] >= 12
        assert result["summary"]["total_folders"] >= 8

        extensions = result["file_extensions"]
        assert ".py" in extensions
        assert ".md" in extensions
        assert ".txt" in extensions

    def test_fd_backend_basic(self, test_directory):
        """Test fd backend basic functionality."""
        fd = FdIntegration()
        if not fd.is_available():
            pytest.skip("fd not available")

        profiler_cfg = DirectoryProfilerConfig(search_backend="fd", show_progress=False)
        profiler = DirectoryProfiler(profiler_cfg)
        result = profiler.probe(test_directory)

        assert result["summary"]["total_files"] >= 12
        assert result["summary"]["total_folders"] >= 8

    def test_backend_consistency(self, test_directory):
        """Test that different backends produce consistent results."""
        fd = FdIntegration()

        results = {}

        profiler_py = DirectoryProfiler(DirectoryProfilerConfig(search_backend="python", show_progress=False))
        results["python"] = profiler_py.probe(test_directory)

        try:
            profiler_rust = DirectoryProfiler(DirectoryProfilerConfig(search_backend="rust", show_progress=False))
            rust_result = profiler_rust.probe(test_directory)
            results["rust"] = rust_result
        except Exception:
            pass

        if fd.is_available():
            profiler_fd = DirectoryProfiler(DirectoryProfilerConfig(search_backend="fd", show_progress=False))
            results["fd"] = profiler_fd.probe(test_directory)

        if len(results) >= 2:
            backend_names = list(results.keys())
            base_result = results[backend_names[0]]

            for backend_name in backend_names[1:]:
                compare_result = results[backend_name]

                base_files = base_result["summary"]["total_files"]
                compare_files = compare_result["summary"]["total_files"]
                assert abs(base_files - compare_files) <= 2

                base_folders = base_result["summary"]["total_folders"]
                compare_folders = compare_result["summary"]["total_folders"]
                assert abs(base_folders - compare_folders) <= 2

    def test_performance_comparison(self, test_directory):
        """Compare performance between backends."""
        fd = FdIntegration()

        performance_results = {}

        profiler_py = DirectoryProfiler(DirectoryProfilerConfig(search_backend="python", show_progress=False))
        start_time = time.time()
        result_py = profiler_py.probe(test_directory)
        py_time = time.time() - start_time
        performance_results["python"] = {"time": py_time, "files": result_py["summary"]["total_files"]}

        try:
            profiler_rust = DirectoryProfiler(DirectoryProfilerConfig(search_backend="rust", show_progress=False))
            start_time = time.time()
            result_rust = profiler_rust.probe(test_directory)
            rust_time = time.time() - start_time
            performance_results["rust"] = {"time": rust_time, "files": result_rust["summary"]["total_files"]}
        except Exception:
            pass

        if fd.is_available():
            profiler_fd = DirectoryProfiler(DirectoryProfilerConfig(search_backend="fd", show_progress=False))
            start_time = time.time()
            result_fd = profiler_fd.probe(test_directory)
            fd_time = time.time() - start_time
            performance_results["fd"] = {"time": fd_time, "files": result_fd["summary"]["total_files"]}

        assert len(performance_results) >= 1

        print("\n🚀 Performance Comparison:")
        for backend, perf in performance_results.items():
            files_per_sec = perf["files"] / perf["time"] if perf["time"] > 0 else 0
            print(f"  {backend}: {perf['time']:.3f}s ({perf['files']} files, {files_per_sec:.0f} files/sec)")

    def test_auto_backend_selection(self, test_directory):
        """Test that auto backend selection works correctly."""
        profiler = DirectoryProfiler(DirectoryProfilerConfig(show_progress=False))
        result = profiler.probe(test_directory)

        assert result["summary"]["total_files"] >= 12
        assert result["summary"]["total_folders"] >= 8

        chosen_backend = profiler._choose_backend()
        print(f"\n🤖 Auto selection chose: {chosen_backend}")

        fd = FdIntegration()
        if hasattr(profiler, "_probe_rust") and profiler.use_rust:
            assert chosen_backend == "rust"
        elif profiler.use_fd and fd.is_available():
            assert chosen_backend == "fd"
        else:
            assert chosen_backend == "python"

    def test_max_depth_consistency(self, test_directory):
        """Test max_depth parameter across backends."""
        max_depth = 2

        backends_to_test = []

        backends_to_test.append(("python", DirectoryProfiler(DirectoryProfilerConfig(search_backend="python", show_progress=False))))

        try:
            backends_to_test.append(("rust", DirectoryProfiler(DirectoryProfilerConfig(search_backend="rust", show_progress=False))))
        except Exception:
            pass

        if FdIntegration().is_available():
            backends_to_test.append(("fd", DirectoryProfiler(DirectoryProfilerConfig(search_backend="fd", show_progress=False))))

        results = {}
        for backend_name, profiler in backends_to_test:
            result = profiler.probe(test_directory, max_depth=max_depth)
            results[backend_name] = result

        if len(results) >= 2:
            backend_names = list(results.keys())

            for i in range(len(backend_names)):
                for j in range(i + 1, len(backend_names)):
                    backend1, backend2 = backend_names[i], backend_names[j]
                    result1, result2 = results[backend1], results[backend2]

                    files_diff = abs(result1["summary"]["total_files"] - result2["summary"]["total_files"])
                    folders_diff = abs(result1["summary"]["total_folders"] - result2["summary"]["total_folders"])

                    if files_diff > 6:
                        print(f"\nDEBUG: Large file count difference between {backend1} and {backend2}")
                        print(f"  {backend1}: {result1['summary']['total_files']} files")
                        print(f"  {backend2}: {result2['summary']['total_files']} files")
                        print(f"  Difference: {files_diff}")

                    assert files_diff <= 6
                    assert folders_diff <= 4


class TestFdFinder:
    """Test FdFinder interface thoroughly."""

    @pytest.fixture
    def test_directory(self):
        """Create test directory for FdFinder tests."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            files = {
                "test.py": "print('hello')",
                "main.py": "def main(): pass",
                "config.json": '{"setting": true}',
                "data.csv": "col1,col2\n1,2",
                "README.md": "# Test",
                "nested/deep.py": "# nested python file",
                "nested/image.png": "fake png",
                ".hidden.txt": "hidden file",
            }

            for file_path, content in files.items():
                full_path = tmp_path / file_path
                full_path.parent.mkdir(parents=True, exist_ok=True)
                full_path.write_text(content)

            yield str(tmp_path)

    def test_fd_finder_basic(self, test_directory):
        """Test basic FdFinder functionality."""
        searcher = FdFinder()
        if not searcher.is_available():
            pytest.skip("fd not available")

        py_files = searcher.find_files(pattern=".*\\.py$", path=test_directory)
        assert len(py_files) >= 3

    def test_fd_finder_patterns(self, test_directory):
        """Test different pattern types in FdFinder."""
        searcher = FdFinder()
        if not searcher.is_available():
            pytest.skip("fd not available")

        py_files_glob = searcher.find_files(pattern="*.py", path=test_directory, use_glob=True)
        assert len(py_files_glob) >= 2

        py_files_regex = searcher.find_files(pattern=".*\\.py$", path=test_directory, use_glob=False)
        assert len(py_files_regex) >= 2

        readme_files = searcher.find_files(pattern="readme", path=test_directory, case_sensitive=False)
        assert len(readme_files) >= 1

    def test_fd_finder_directories(self, test_directory):
        """Test directory finding with FdFinder."""
        searcher = FdFinder()
        if not searcher.is_available():
            pytest.skip("fd not available")

        dirs = searcher.find_directories(pattern="nested", path=test_directory)
        assert len(dirs) >= 1
        assert any("nested" in str(d) for d in dirs)

    def test_fd_finder_hidden_files(self, test_directory):
        """Test hidden file handling."""
        searcher = FdFinder()
        if not searcher.is_available():
            pytest.skip("fd not available")

        hidden_files = searcher.find_files(pattern=".*", path=test_directory, hidden=True)
        hidden_names = [Path(f).name for f in hidden_files]
        assert any(name.startswith(".") for name in hidden_names)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
