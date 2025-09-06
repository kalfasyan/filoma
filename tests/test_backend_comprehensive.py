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
from filoma.directories import DirectoryProfiler, FdFinder


class TestBackendComprehensive:
    """Comprehensive backend testing suite."""

    @pytest.fixture
    def test_directory(self):
        """Create a complex test directory structure."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            # Create a complex directory structure
            # Root
            # ├── docs/
            # │   ├── README.md
            # │   ├── guide.txt
            # │   └── images/
            # │       ├── logo.png
            # │       └── diagram.jpg
            # ├── src/
            # │   ├── main.py
            # │   ├── utils.py
            # │   └── modules/
            # │       ├── __init__.py
            # │       ├── core.py
            # │       └── helpers.rs
            # ├── tests/
            # │   ├── test_main.py
            # │   └── test_utils.py
            # ├── empty_dir/
            # ├── data/
            # │   ├── large_file.txt (1KB)
            # │   └── small.json
            # └── .hidden/
            #     └── secret.txt

            # Create directories
            dirs = ["docs", "docs/images", "src", "src/modules", "tests", "empty_dir", "data", ".hidden"]
            for dir_name in dirs:
                (tmp_path / dir_name).mkdir(parents=True, exist_ok=True)

            # Create files with different sizes and types
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
                "data/large_file.txt": "x" * 1000,  # 1KB file
                "data/small.json": '{"key": "value"}',
                ".hidden/secret.txt": "secret content",
            }

            for file_path, content in files.items():
                (tmp_path / file_path).write_text(content)

            yield str(tmp_path)

    def test_python_backend_basic(self, test_directory):
        """Test Python backend basic functionality."""
        profiler = DirectoryProfiler(search_backend="python", show_progress=False)
        result = profiler.probe(test_directory)

        # Verify basic counts
        assert result["summary"]["total_files"] >= 12  # At least our created files
        assert result["summary"]["total_folders"] >= 8  # Including root and created dirs
        assert result["summary"]["empty_folder_count"] >= 1  # empty_dir

        # Verify extensions are detected
        extensions = result["file_extensions"]
        assert ".py" in extensions
        assert ".md" in extensions
        assert ".txt" in extensions
        assert ".rs" in extensions

        # Verify empty folders are detected
        empty_folders = [Path(p).name for p in result["empty_folders"]]
        assert "empty_dir" in empty_folders

    @pytest.mark.skipif(not hasattr(DirectoryProfiler(show_progress=False), "_probe_rust"), reason="Rust backend not available")
    def test_rust_backend_basic(self, test_directory):
        """Test Rust backend basic functionality."""
        profiler = DirectoryProfiler(search_backend="rust", show_progress=False)
        result = profiler.probe(test_directory)

        # Verify basic counts
        assert result["summary"]["total_files"] >= 12
        assert result["summary"]["total_folders"] >= 8

        # Verify extensions are detected
        extensions = result["file_extensions"]
        assert ".py" in extensions
        assert ".md" in extensions
        assert ".txt" in extensions

    def test_fd_backend_basic(self, test_directory):
        """Test fd backend basic functionality."""
        fd = FdIntegration()
        if not fd.is_available():
            pytest.skip("fd not available")

        profiler = DirectoryProfiler(search_backend="fd", show_progress=False)
        result = profiler.probe(test_directory)

        # Verify basic counts
        assert result["summary"]["total_files"] >= 12
        assert result["summary"]["total_folders"] >= 8

    def test_backend_consistency(self, test_directory):
        """Test that different backends produce consistent results."""
        fd = FdIntegration()

        # Get results from available backends
        results = {}

        # Python (always available)
        profiler_py = DirectoryProfiler(search_backend="python", show_progress=False)
        results["python"] = profiler_py.probe(test_directory)

        # Rust (if available)
        try:
            profiler_rust = DirectoryProfiler(search_backend="rust", show_progress=False)
            rust_result = profiler_rust.probe(test_directory)
            results["rust"] = rust_result
        except Exception:
            pass

        # fd (if available)
        if fd.is_available():
            profiler_fd = DirectoryProfiler(search_backend="fd", show_progress=False)
            results["fd"] = profiler_fd.probe(test_directory)

        # Compare results between backends
        if len(results) >= 2:
            backend_names = list(results.keys())
            base_result = results[backend_names[0]]

            for backend_name in backend_names[1:]:
                compare_result = results[backend_name]

                # File counts should be very close (within small margin for hidden files)
                base_files = base_result["summary"]["total_files"]
                compare_files = compare_result["summary"]["total_files"]
                assert abs(base_files - compare_files) <= 2, f"File count mismatch: {backend_names[0]}={base_files}, {backend_name}={compare_files}"

                # Folder counts should be close
                base_folders = base_result["summary"]["total_folders"]
                compare_folders = compare_result["summary"]["total_folders"]
                assert abs(base_folders - compare_folders) <= 2, (
                    f"Folder count mismatch: {backend_names[0]}={base_folders}, {backend_name}={compare_folders}"
                )

    def test_performance_comparison(self, test_directory):
        """Compare performance between backends."""
        fd = FdIntegration()

        performance_results = {}

        # Test Python
        profiler_py = DirectoryProfiler(search_backend="python", show_progress=False)
        start_time = time.time()
        result_py = profiler_py.probe(test_directory)
        py_time = time.time() - start_time
        performance_results["python"] = {"time": py_time, "files": result_py["summary"]["total_files"]}

        # Test Rust (if available)
        try:
            profiler_rust = DirectoryProfiler(search_backend="rust", show_progress=False)
            start_time = time.time()
            result_rust = profiler_rust.probe(test_directory)
            rust_time = time.time() - start_time
            performance_results["rust"] = {"time": rust_time, "files": result_rust["summary"]["total_files"]}
        except Exception:
            pass

        # Test fd (if available)
        if fd.is_available():
            profiler_fd = DirectoryProfiler(search_backend="fd", show_progress=False)
            start_time = time.time()
            result_fd = profiler_fd.probe(test_directory)
            fd_time = time.time() - start_time
            performance_results["fd"] = {"time": fd_time, "files": result_fd["summary"]["total_files"]}

        # Verify we have results
        assert len(performance_results) >= 1

        # Print performance comparison for manual verification
        print("\n🚀 Performance Comparison:")
        for backend, perf in performance_results.items():
            files_per_sec = perf["files"] / perf["time"] if perf["time"] > 0 else 0
            print(f"  {backend}: {perf['time']:.3f}s ({perf['files']} files, {files_per_sec:.0f} files/sec)")

    def test_auto_backend_selection(self, test_directory):
        """Test that auto backend selection works correctly."""
        profiler = DirectoryProfiler(show_progress=False)  # Uses auto selection
        result = profiler.probe(test_directory)

        # Should successfully probe the directory
        assert result["summary"]["total_files"] >= 12
        assert result["summary"]["total_folders"] >= 8

        # Verify which backend was chosen
        chosen_backend = profiler._choose_backend()
        print(f"\n🤖 Auto selection chose: {chosen_backend}")

        # Should prefer Rust > fd > Python unless fd is explicitly enabled
        fd = FdIntegration()
        # Prefer Rust when available and enabled
        if hasattr(profiler, "_probe_rust") and profiler.use_rust:
            assert chosen_backend == "rust", "Auto selection should prefer Rust when available"
        # Otherwise prefer fd when enabled and available
        elif profiler.use_fd and fd.is_available():
            assert chosen_backend == "fd", "Auto selection should prefer fd when explicitly enabled"
        else:
            assert chosen_backend == "python", "Auto selection should fall back to Python"

    def test_max_depth_consistency(self, test_directory):
        """Test max_depth parameter across backends."""
        max_depth = 2

        # Test available backends with max_depth
        backends_to_test = []

        # Python
        profiler_py = DirectoryProfiler(search_backend="python", show_progress=False)
        backends_to_test.append(("python", profiler_py))

        # Rust (if available)
        try:
            profiler_rust = DirectoryProfiler(search_backend="rust", show_progress=False)
            backends_to_test.append(("rust", profiler_rust))
        except Exception:
            pass

        # fd (if available)
        fd = FdIntegration()
        if fd.is_available():
            profiler_fd = DirectoryProfiler(search_backend="fd", show_progress=False)
            backends_to_test.append(("fd", profiler_fd))

        results = {}
        for backend_name, profiler in backends_to_test:
            result = profiler.probe(test_directory, max_depth=max_depth)
            results[backend_name] = result

        # Compare results between backends
        if len(results) >= 2:
            backend_names = list(results.keys())

            for i in range(len(backend_names)):
                for j in range(i + 1, len(backend_names)):
                    backend1, backend2 = backend_names[i], backend_names[j]
                    result1, result2 = results[backend1], results[backend2]

                    # Results should be reasonably close
                    files_diff = abs(result1["summary"]["total_files"] - result2["summary"]["total_files"])
                    folders_diff = abs(result1["summary"]["total_folders"] - result2["summary"]["total_folders"])

                    # Debug output for failed tests
                    if files_diff > 6:
                        print(f"\nDEBUG: Large file count difference between {backend1} and {backend2}")
                        print(f"  {backend1}: {result1['summary']['total_files']} files")
                        print(f"  {backend2}: {result2['summary']['total_files']} files")
                        print(f"  Difference: {files_diff}")

                    assert files_diff <= 6, (
                        f"Max depth file count difference too large: {backend1} vs {backend2} "
                        f"(files: {result1['summary']['total_files']} vs {result2['summary']['total_files']})"
                    )
                    assert folders_diff <= 4, (
                        f"Max depth folder count difference too large: {backend1} vs {backend2} "
                        f"(folders: {result1['summary']['total_folders']} vs {result2['summary']['total_folders']})"
                    )


class TestFdFinder:
    """Test FdFinder interface thoroughly."""

    @pytest.fixture
    def test_directory(self):
        """Create test directory for FdFinder tests."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            # Create test files
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

        # Test finding Python files
        py_files = searcher.find_files(pattern=".*\\.py$", path=test_directory)
        assert len(py_files) >= 3  # test.py, main.py, nested/deep.py

        # Test finding by extension
        json_files = searcher.find_by_extension([".json"], path=test_directory)
        assert len(json_files) >= 1  # config.json

    def test_fd_finder_patterns(self, test_directory):
        """Test different pattern types in FdFinder."""
        searcher = FdFinder()
        if not searcher.is_available():
            pytest.skip("fd not available")

        # Test glob pattern
        py_files_glob = searcher.find_files(pattern="*.py", path=test_directory, use_glob=True)
        assert len(py_files_glob) >= 2

        # Test regex pattern
        py_files_regex = searcher.find_files(pattern=".*\\.py$", path=test_directory, use_glob=False)
        assert len(py_files_regex) >= 2

        # Test case insensitive
        readme_files = searcher.find_files(pattern="readme", path=test_directory, case_sensitive=False)
        assert len(readme_files) >= 1

    def test_fd_finder_directories(self, test_directory):
        """Test directory finding with FdFinder."""
        searcher = FdFinder()
        if not searcher.is_available():
            pytest.skip("fd not available")

        # Find directories
        dirs = searcher.find_directories(pattern="nested", path=test_directory)
        assert len(dirs) >= 1
        assert any("nested" in str(d) for d in dirs)

    def test_fd_finder_hidden_files(self, test_directory):
        """Test hidden file handling."""
        searcher = FdFinder()
        if not searcher.is_available():
            pytest.skip("fd not available")

        # Find hidden files
        hidden_files = searcher.find_files(pattern=".*", path=test_directory, hidden=True)

        # Should find at least our .hidden.txt file
        hidden_names = [Path(f).name for f in hidden_files]
        assert any(name.startswith(".") for name in hidden_names)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
