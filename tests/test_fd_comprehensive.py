#!/usr/bin/env python3
"""
Comprehensive fd backend tests for filoma.

Tests specifically targeting fd backend functionality, pattern matching,
and integration with the fd command-line tool.
"""

import tempfile
import time
from pathlib import Path

import pytest

from filoma.core import FdIntegration
from filoma.directories import DirectoryProfiler, FdFinder


class TestFdBackend:
    """Comprehensive fd backend testing."""

    @pytest.fixture
    def complex_test_structure(self):
        """Create a complex test structure for fd testing."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            # Create a structure with various file types and patterns
            files = {
                # Python files
                "main.py": "def main():\n    print('hello')",
                "src/utils.py": "def helper(): pass",
                "src/__init__.py": "",
                "tests/test_main.py": "def test(): assert True",
                "scripts/deploy.py": "# deployment script",
                # Config files
                "config.json": '{"setting": true}',
                "settings.yaml": "debug: true",
                ".env": "SECRET=value",
                "docker-compose.yml": "version: '3'",
                # Documentation
                "README.md": "# Project",
                "docs/guide.md": "## Guide",
                "docs/api.rst": "API Documentation",
                # Data files
                "data/sample.csv": "name,age\nJohn,30",
                "data/large.txt": "x" * 5000,
                "logs/app.log": "INFO: Application started",
                # Images
                "assets/logo.png": "fake png data",
                "assets/banner.jpg": "fake jpg data",
                "icons/favicon.ico": "fake ico",
                # Hidden files
                ".gitignore": "*.pyc\n__pycache__/",
                ".hidden/secret.txt": "hidden content",
                "src/.cache/temp": "cache data",
                # Special characters in names
                "file with spaces.txt": "spaces in name",
                "file-with-dashes.js": "console.log('test')",
                "file_with_underscores.rs": "fn main() {}",
            }

            # Create all files
            for file_path, content in files.items():
                full_path = tmp_path / file_path
                full_path.parent.mkdir(parents=True, exist_ok=True)
                full_path.write_text(content)

            # Create some empty directories
            (tmp_path / "empty_dir").mkdir()
            (tmp_path / "another_empty").mkdir()

            yield str(tmp_path)

    def test_fd_availability(self):
        """Test fd command availability."""
        fd = FdIntegration()
        if not fd.is_available():
            pytest.skip("fd command not available")

        # Should be able to get version
        version = fd.get_version()
        assert version is not None
        assert "fd" in version.lower()

    def test_fd_basic_search(self, complex_test_structure):
        """Test basic fd search functionality."""
        fd = FdIntegration()
        if not fd.is_available():
            pytest.skip("fd command not available")

        # Test finding all Python files
        py_files = fd.find(pattern=".*\\.py$", path=complex_test_structure)
        py_file_names = [Path(f).name for f in py_files]

        assert "main.py" in py_file_names
        assert "utils.py" in py_file_names
        assert "__init__.py" in py_file_names
        assert len(py_files) >= 5

    def test_fd_glob_patterns(self, complex_test_structure):
        """Test fd with glob patterns."""
        fd = FdIntegration()
        if not fd.is_available():
            pytest.skip("fd command not available")

        # Test glob pattern for Python files
        py_files_glob = fd.find(pattern="*.py", path=complex_test_structure, use_glob=True)
        assert len(py_files_glob) >= 5

        # Test glob pattern for config files
        config_files = fd.find(pattern="*.{json,yaml,yml}", path=complex_test_structure, use_glob=True)
        config_names = [Path(f).name for f in config_files]
        assert "config.json" in config_names
        assert any("yaml" in name or "yml" in name for name in config_names)

    def test_fd_regex_patterns(self, complex_test_structure):
        """Test fd with regex patterns."""
        fd = FdIntegration()
        if not fd.is_available():
            pytest.skip("fd command not available")

        # Test regex for files with extensions
        files_with_ext = fd.find(pattern=".*\\.(py|js|rs)$", path=complex_test_structure, use_glob=False)
        assert len(files_with_ext) >= 6  # py, js, rs files

        # Test regex for files with specific patterns
        dash_files = fd.find(pattern=".*-.*\\.(js|txt)$", path=complex_test_structure, use_glob=False)
        dash_names = [Path(f).name for f in dash_files]
        assert "file-with-dashes.js" in dash_names

    def test_fd_file_type_filtering(self, complex_test_structure):
        """Test fd file type filtering."""
        fd = FdIntegration()
        if not fd.is_available():
            pytest.skip("fd command not available")

        # Test files only
        files_only = fd.find(pattern=".", path=complex_test_structure, file_types=["f"])
        # Should not include directories
        for file_path in files_only:
            assert Path(file_path).is_file()

        # Test directories only
        dirs_only = fd.find(pattern=".", path=complex_test_structure, file_types=["d"])
        # Should not include files
        for dir_path in dirs_only:
            assert Path(dir_path).is_dir()

    def test_fd_hidden_files(self, complex_test_structure):
        """Test fd hidden file handling."""
        fd = FdIntegration()
        if not fd.is_available():
            pytest.skip("fd command not available")

        # Test finding hidden files
        hidden_files = fd.find(pattern="\\.", path=complex_test_structure, search_hidden=True)
        hidden_names = [Path(f).name for f in hidden_files]
        assert any(name.startswith(".") for name in hidden_names)

        # Test without hidden files (default)
        normal_files = fd.find(pattern=".*\\.txt$", path=complex_test_structure, search_hidden=False)
        normal_names = [Path(f).name for f in normal_files]
        # Should find regular txt files but not hidden ones
        assert "large.txt" in normal_names
        assert "file with spaces.txt" in normal_names

    def test_fd_max_depth(self, complex_test_structure):
        """Test fd max depth functionality."""
        fd = FdIntegration()
        if not fd.is_available():
            pytest.skip("fd command not available")

        # Test depth 1 (only immediate children)
        depth1_files = fd.find(pattern=".*\\.py$", path=complex_test_structure, max_depth=1)
        depth1_names = [Path(f).name for f in depth1_files]
        assert "main.py" in depth1_names  # Should find root level file

        # Test deeper search
        deep_files = fd.find(pattern=".*\\.py$", path=complex_test_structure, max_depth=3)
        deep_names = [Path(f).name for f in deep_files]
        assert "utils.py" in deep_names  # Should find nested files
        assert len(deep_files) >= len(depth1_files)

    def test_fd_max_results(self, complex_test_structure):
        """Test fd max results limiting."""
        fd = FdIntegration()
        if not fd.is_available():
            pytest.skip("fd command not available")

        # Test limiting results
        limited_files = fd.find(pattern=".*", path=complex_test_structure, max_results=5)
        assert len(limited_files) <= 5

        # Test unlimited
        all_files = fd.find(pattern=".*", path=complex_test_structure, file_types=["f"])
        assert len(all_files) >= 15  # Should find all our test files

    def test_fd_case_sensitivity(self, complex_test_structure):
        """Test fd case sensitivity."""
        fd = FdIntegration()
        if not fd.is_available():
            pytest.skip("fd command not available")

        # Create a file with mixed case
        test_path = Path(complex_test_structure)
        (test_path / "MixedCase.TXT").write_text("mixed case content")

        # Test case sensitive search
        case_sensitive = fd.find(pattern=".*\\.txt$", path=complex_test_structure, case_sensitive=True)

        # Test case insensitive search
        case_insensitive = fd.find(pattern=".*\\.txt$", path=complex_test_structure, case_sensitive=False)

        # Case insensitive should find more files
        assert len(case_insensitive) >= len(case_sensitive)

    def test_fd_directory_profiler_integration(self, complex_test_structure):
        """Test fd backend integration with DirectoryProfiler."""
        fd = FdIntegration()
        if not fd.is_available():
            pytest.skip("fd command not available")

        profiler = DirectoryProfiler(search_backend="fd", show_progress=False)
        result = profiler.probe(complex_test_structure)

        # Should find all our test files
        assert result["summary"]["total_files"] >= 20
        assert result["summary"]["total_folders"] >= 10

        # Should detect file extensions
        extensions = result["file_extensions"]
        assert ".py" in extensions
        assert ".json" in extensions
        assert ".md" in extensions
        assert ".txt" in extensions

        # Should detect empty directories
        assert result["summary"]["empty_folder_count"] >= 2

    def test_fd_vs_python_consistency(self, complex_test_structure):
        """Test fd vs Python backend consistency."""
        fd = FdIntegration()
        if not fd.is_available():
            pytest.skip("fd command not available")

        # Test Python backend
        profiler_py = DirectoryProfiler(search_backend="python", show_progress=False)
        result_py = profiler_py.probe(complex_test_structure)

        # Test fd backend
        profiler_fd = DirectoryProfiler(search_backend="fd", show_progress=False)
        result_fd = profiler_fd.probe(complex_test_structure)

        # Results should be reasonably close
        # (small differences acceptable due to hidden file handling)
        py_files = result_py["summary"]["total_files"]
        fd_files = result_fd["summary"]["total_files"]
        assert abs(py_files - fd_files) <= 5, f"File count difference too large: Python={py_files}, fd={fd_files}"

        py_folders = result_py["summary"]["total_folders"]
        fd_folders = result_fd["summary"]["total_folders"]
        assert abs(py_folders - fd_folders) <= 2, f"Folder count difference too large: Python={py_folders}, fd={fd_folders}"

        # Extensions should largely overlap
        py_exts = set(result_py["file_extensions"].keys())
        fd_exts = set(result_fd["file_extensions"].keys())
        common_exts = py_exts.intersection(fd_exts)
        assert len(common_exts) >= len(py_exts) * 0.8, "Extension detection should be consistent"

    def test_fd_performance_vs_python(self, complex_test_structure):
        """Test fd vs Python performance."""
        fd = FdIntegration()
        if not fd.is_available():
            pytest.skip("fd command not available")

        # Test Python performance
        profiler_py = DirectoryProfiler(search_backend="python", show_progress=False)
        start_py = time.time()
        result_py = profiler_py.probe(complex_test_structure)
        time_py = time.time() - start_py

        # Test fd performance
        profiler_fd = DirectoryProfiler(search_backend="fd", show_progress=False)
        start_fd = time.time()
        result_fd = profiler_fd.probe(complex_test_structure)
        time_fd = time.time() - start_fd

        print("\n🚀 Performance Comparison:")
        print(f"  Python: {time_py:.3f}s ({result_py['summary']['total_files']} files)")
        print(f"  fd: {time_fd:.3f}s ({result_fd['summary']['total_files']} files)")

        if time_py > 0 and time_fd > 0:
            speedup = time_py / time_fd
            print(f"  fd speedup: {speedup:.2f}x")

            # For small datasets, performance might be similar or fd might even be slower
            # We're mainly testing that fd doesn't crash and produces results
            assert speedup >= 0.01, "fd performance unexpectedly poor"

    def test_fd_finder_interface(self, complex_test_structure):
        """Test FdFinder high-level interface."""
        searcher = FdFinder()
        if not searcher.is_available():
            pytest.skip("FdFinder not available")

        # Test finding files by extension
        py_files = searcher.find_by_extension([".py"], path=complex_test_structure)
        assert len(py_files) >= 5

        # Test finding files by multiple extensions
        code_files = searcher.find_by_extension([".py", ".js", ".rs"], path=complex_test_structure)
        assert len(code_files) >= 6

        # Test finding directories
        dirs = searcher.find_directories(pattern=".*", path=complex_test_structure)
        assert len(dirs) >= 8

        # Test glob pattern
        config_files = searcher.find_files(pattern="*.{json,yaml,yml}", path=complex_test_structure, use_glob=True)
        assert len(config_files) >= 2

    def test_fd_error_handling(self):
        """Test fd error handling."""
        fd = FdIntegration()
        if not fd.is_available():
            pytest.skip("fd command not available")

        # Test with non-existent directory - check that it returns empty or raises
        try:
            result = fd.find(pattern=".*", path="/nonexistent/path")
            # If it doesn't raise an error, result should be empty
            assert isinstance(result, list)
            assert len(result) == 0, "Should return empty list for non-existent directory"
        except Exception:
            # This is also acceptable - fd should handle this gracefully
            pass

        # Test with invalid pattern (should handle gracefully or raise clear error)
        try:
            result = fd.find(pattern="[invalid", path=".")
            # If it doesn't raise an error, result should be empty or valid
            assert isinstance(result, list)
        except Exception as e:
            # Should raise a clear, understandable error
            error_msg = str(e).lower()
            assert any(word in error_msg for word in ["pattern", "regex", "invalid", "syntax"]), f"Error message should be clear: {e}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
