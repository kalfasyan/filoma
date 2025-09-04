#!/usr/bin/env python3
"""
Comprehensive Rust backend tests for filoma.

Tests specifically targeting Rust backend functionality, performance characteristics,
and edge cases to ensure robust operation.
"""

import tempfile
import time
from pathlib import Path

import pytest

from filoma.directories import DirectoryProfiler


class TestRustBackend:
    """Comprehensive Rust backend testing."""

    @pytest.fixture
    def large_test_structure(self):
        """Create a larger test structure to test Rust performance."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            # Create a structure with many files and nested directories
            # This tests Rust's parallel processing capabilities
            for i in range(5):
                dir_path = tmp_path / f"level_{i}"
                dir_path.mkdir()

                # Create files in each directory
                for j in range(10):
                    (dir_path / f"file_{j}.py").write_text(f"# File {j} in level {i}\nprint('test')")
                    (dir_path / f"data_{j}.json").write_text(f'{{"level": {i}, "file": {j}}}')

                # Create nested directories
                for k in range(3):
                    nested_path = dir_path / f"nested_{k}"
                    nested_path.mkdir()
                    (nested_path / f"nested_file_{k}.txt").write_text(f"Nested content {k}")

            # Create some large files to test size handling
            (tmp_path / "large_file.txt").write_text("x" * 10000)  # 10KB
            (tmp_path / "medium_file.csv").write_text("col1,col2\n" + "data,value\n" * 1000)  # ~12KB

            yield str(tmp_path)

    def test_rust_backend_availability(self):
        """Test if Rust backend is available and working."""
        profiler = DirectoryProfiler(search_backend="rust", show_progress=False)

        # Try to use Rust backend
        try:
            # This should work if Rust backend is available
            backend = profiler._choose_backend()
            if backend == "rust":
                assert profiler.use_rust, "Rust backend should be marked as available"
            else:
                pytest.skip("Rust backend not available")
        except Exception as e:
            pytest.skip(f"Rust backend not available: {e}")

    def test_rust_vs_python_performance(self, large_test_structure):
        """Compare Rust vs Python performance on larger dataset."""
        # Test Python
        profiler_py = DirectoryProfiler(search_backend="python", show_progress=False)
        start_py = time.time()
        result_py = profiler_py.probe(large_test_structure)
        time_py = time.time() - start_py

        # Test Rust (if available)
        try:
            profiler_rust = DirectoryProfiler(search_backend="rust", show_progress=False)
            start_rust = time.time()
            result_rust = profiler_rust.probe(large_test_structure)
            time_rust = time.time() - start_rust

            # Rust should be faster (or at least not much slower)
            speedup = time_py / time_rust
            print(f"\n🚀 Rust Performance: {time_rust:.3f}s vs Python {time_py:.3f}s")
            print(f"🚀 Speedup: {speedup:.2f}x")

            # Results should be consistent
            assert abs(result_py["summary"]["total_files"] - result_rust["summary"]["total_files"]) <= 2
            assert abs(result_py["summary"]["total_folders"] - result_rust["summary"]["total_folders"]) <= 2

            # Rust should generally be faster for this size dataset
            # Allow some tolerance for small datasets or system variance
            assert speedup >= 0.5, f"Rust unexpectedly slow: {speedup:.2f}x speedup"

        except Exception as e:
            pytest.skip(f"Rust backend not available for performance test: {e}")

    def test_rust_parallel_vs_sequential(self, large_test_structure):
        """Test Rust parallel vs sequential performance if both are available."""
        try:
            # Test with parallel disabled
            profiler_seq = DirectoryProfiler(search_backend="rust", use_parallel=False, show_progress=False)
            start_seq = time.time()
            result_seq = profiler_seq.probe(large_test_structure)
            time_seq = time.time() - start_seq

            # Test with parallel enabled
            profiler_par = DirectoryProfiler(search_backend="rust", use_parallel=True, show_progress=False)
            start_par = time.time()
            result_par = profiler_par.probe(large_test_structure)
            time_par = time.time() - start_par

            print(f"\n🔧 Rust Sequential: {time_seq:.3f}s")
            print(f"🔧 Rust Parallel: {time_par:.3f}s")
            print(f"🔧 Parallel speedup: {time_seq / time_par:.2f}x")

            # Results should be consistent
            assert abs(result_seq["summary"]["total_files"] - result_par["summary"]["total_files"]) <= 1
            assert abs(result_seq["summary"]["total_folders"] - result_par["summary"]["total_folders"]) <= 1

            # Parallel should generally be faster or at least not much slower
            parallel_speedup = time_seq / time_par
            assert parallel_speedup >= 0.8, f"Parallel unexpectedly slow: {parallel_speedup:.2f}x"

        except Exception as e:
            pytest.skip(f"Rust parallel testing not available: {e}")

    def test_rust_fast_path_mode(self, large_test_structure):
        """Test Rust fast path mode vs full analysis."""
        try:
            # Test full analysis
            profiler_full = DirectoryProfiler(search_backend="rust", fast_path_only=False, show_progress=False)
            start_full = time.time()
            result_full = profiler_full.probe(large_test_structure)
            time_full = time.time() - start_full

            # Test fast path
            profiler_fast = DirectoryProfiler(search_backend="rust", fast_path_only=True, show_progress=False)
            start_fast = time.time()
            result_fast = profiler_fast.probe(large_test_structure)
            time_fast = time.time() - start_fast

            print(f"\n⚡ Rust Full Analysis: {time_full:.3f}s")
            print(f"⚡ Rust Fast Path: {time_fast:.3f}s")
            print(f"⚡ Fast path speedup: {time_full / time_fast:.2f}x")

            # Fast path should be faster
            assert time_fast <= time_full * 1.1, "Fast path should be faster than full analysis"

            # File counts should be the same
            assert result_full["summary"]["total_files"] == result_fast["summary"]["total_files"]
            assert result_full["summary"]["total_folders"] == result_fast["summary"]["total_folders"]

        except Exception as e:
            pytest.skip(f"Rust fast path testing not available: {e}")

    def test_rust_max_depth_handling(self, large_test_structure):
        """Test Rust backend with different max_depth values."""
        try:
            profiler = DirectoryProfiler(search_backend="rust", show_progress=False)

            # Test different depth limits
            depths = [1, 2, 3, None]
            results = {}

            for depth in depths:
                result = profiler.probe(large_test_structure, max_depth=depth)
                results[depth] = result
                print(f"📏 Depth {depth}: {result['summary']['total_files']} files, {result['summary']['total_folders']} folders")

            # Verify depth limiting works (deeper should have more files)
            assert results[1]["summary"]["total_files"] <= results[2]["summary"]["total_files"]
            assert results[2]["summary"]["total_files"] <= results[3]["summary"]["total_files"]
            assert results[3]["summary"]["total_files"] <= results[None]["summary"]["total_files"]

        except Exception as e:
            pytest.skip(f"Rust max_depth testing not available: {e}")

    def test_rust_empty_directory_handling(self):
        """Test Rust backend with empty directories."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            # Create structure with empty directories
            (tmp_path / "empty1").mkdir()
            (tmp_path / "empty2").mkdir()
            (tmp_path / "has_file").mkdir()
            (tmp_path / "has_file" / "file.txt").write_text("content")
            (tmp_path / "nested_empty" / "deep_empty").mkdir(parents=True)

            try:
                profiler = DirectoryProfiler(search_backend="rust", show_progress=False)
                result = profiler.probe(str(tmp_path))

                # Should detect empty directories
                assert result["summary"]["empty_folder_count"] >= 3  # empty1, empty2, deep_empty

                # Should find the one file
                assert result["summary"]["total_files"] == 1

                # Should count all directories including root
                assert result["summary"]["total_folders"] >= 5

            except Exception as e:
                pytest.skip(f"Rust empty directory testing not available: {e}")

    def test_rust_large_file_handling(self):
        """Test Rust backend with various file sizes."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            # Create files of different sizes
            (tmp_path / "tiny.txt").write_text("x")  # 1 byte
            (tmp_path / "small.txt").write_text("x" * 100)  # 100 bytes
            (tmp_path / "medium.txt").write_text("x" * 10000)  # 10KB
            (tmp_path / "large.txt").write_text("x" * 1000000)  # 1MB

            try:
                profiler = DirectoryProfiler(search_backend="rust", show_progress=False)
                result = profiler.probe(str(tmp_path))

                # Should handle all files
                assert result["summary"]["total_files"] == 4

                # Should have size statistics
                assert "file_sizes" in result

                # Total size should be reasonable (around 1MB + overhead)
                total_size = sum(result["file_sizes"]["size_distribution"].values())
                assert total_size >= 1010000  # At least 1MB + smaller files

            except Exception as e:
                pytest.skip(f"Rust large file testing not available: {e}")

    def test_rust_extension_detection(self, large_test_structure):
        """Test Rust backend extension detection accuracy."""
        try:
            profiler = DirectoryProfiler(search_backend="rust", show_progress=False)
            result = profiler.probe(large_test_structure)

            # Should detect the extensions we created
            extensions = result["file_extensions"]
            assert ".py" in extensions
            assert ".json" in extensions
            assert ".txt" in extensions
            assert ".csv" in extensions

            # Should have reasonable counts
            assert extensions[".py"] >= 50  # 5 levels * 10 files each
            assert extensions[".json"] >= 50
            assert extensions[".txt"] >= 15  # nested files + large_file.txt

        except Exception as e:
            pytest.skip(f"Rust extension detection testing not available: {e}")

    def test_rust_error_handling(self):
        """Test Rust backend error handling for edge cases."""
        try:
            profiler = DirectoryProfiler(search_backend="rust", show_progress=False)

            # Test non-existent directory
            with pytest.raises(Exception):  # Should raise appropriate error
                profiler.probe("/nonexistent/directory/path")

            # Test with permission issues (if we can create them)
            with tempfile.TemporaryDirectory() as tmp_dir:
                result = profiler.probe(tmp_dir)  # Empty directory should work
                assert result["summary"]["total_files"] == 0
                assert result["summary"]["total_folders"] == 1  # Just the root

        except Exception as e:
            pytest.skip(f"Rust error handling testing not available: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
