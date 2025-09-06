#!/usr/bin/env python3
"""
Test script for fd integration in filoma.

This script tests the new fd integration capabilities.
"""

import importlib.util
import sys
import warnings
from pathlib import Path

import pytest

# Add src to path so we can import filoma
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from filoma.core import FdIntegration
from filoma.directories import DirectoryProfiler, FdFinder

# Detect Rust availability by checking module spec (avoids importing at test collection)
RUST_AVAILABLE_LOCAL = importlib.util.find_spec("filoma.filoma_core") is not None

# Warning regex used by multiple tests
WARNING_REGEX = r"^\[filoma\] Progress bar updates are limited"


def test_fd_integration():
    """Test fd integration components."""
    # Suppress known progress warning emitted by the Rust backend during scans,
    # but only for this test so other tests can still assert it.
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=WARNING_REGEX)

        print("🔍 Testing fd Integration\n")

        # Test 1: Check fd availability
        print("1. Checking fd availability...")
        fd = FdIntegration()
    if not fd.is_available():
        pytest.skip("fd not available on this system")
    else:
        print(f"   ✅ fd is available: {fd.get_version()}")

    # Test 2: Basic fd search
    print("\n2. Testing basic fd search...")
    try:
        # Use glob mode for the *.py pattern
        files = fd.find(pattern="*.py", path=".", max_results=5, use_glob=True)
        print(f"   ✅ Found {len(files)} Python files: {files[:3]}{'...' if len(files) > 3 else ''}")
        assert isinstance(files, list)
        assert len(files) > 0
    except Exception as e:
        pytest.fail(f"fd search failed: {e}")

    # Test 3: FdFinder interface
    print("\n3. Testing FdFinder interface...")
    try:
        searcher = FdFinder()
        if searcher.is_available():
            python_files = searcher.find_by_extension(".py", max_depth=2)
            print(f"   ✅ FdFinder found {len(python_files)} Python files")
            assert isinstance(python_files, list)
        else:
            pytest.skip("FdFinder (fd) not available")
    except Exception as e:
        pytest.fail(f"FdFinder failed: {e}")

    # Test 4: DirectoryProfiler with fd backend
    print("\n4. Testing DirectoryProfiler with fd backend...")
    try:
        profiler = DirectoryProfiler(search_backend="fd")
        if not profiler.is_fd_available():
            pytest.skip("DirectoryProfiler fd backend not available")

        print("   ✅ DirectoryProfiler fd backend available")

        # Quick test on current directory
        result = profiler.probe(".", max_depth=2)
        print(f"   ✅ Analysis completed: {result['summary']['total_files']} files found")
        print(f"   ✅ Backend used: {result['timing']['implementation']}")
        assert "summary" in result and "total_files" in result["summary"]
        assert result["summary"]["total_files"] >= 0
        assert "timing" in result and "implementation" in result["timing"]
    except Exception as e:
        pytest.fail(f"DirectoryProfiler fd backend failed: {e}")


def test_backend_comparison():
    #!/usr/bin/env python3
    """
    Test script for fd integration in filoma.

    This script tests the fd integration capabilities.
    """

    import importlib.util
    import sys
    import warnings
    from pathlib import Path

    import pytest

    # Add src to path so we can import filoma
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

    from filoma.core import FdIntegration
    from filoma.directories import DirectoryProfiler, FdFinder

    # Detect Rust availability by checking module spec (avoids importing at test collection)
    RUST_AVAILABLE_LOCAL = importlib.util.find_spec("filoma.filoma_core") is not None

    # Warning regex used by multiple tests
    WARNING_REGEX = r"^\[filoma\] Progress bar updates are limited"

    def test_fd_integration():
        """Test fd integration components."""
        # Suppress known progress warning emitted by the Rust backend during scans,
        # but only for this test so other tests can still assert it.
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=WARNING_REGEX)

            print("🔍 Testing fd Integration\n")

            # Test 1: Check fd availability
            print("1. Checking fd availability...")
            fd = FdIntegration()

            if not fd.is_available():
                pytest.skip("fd not available on this system")
            else:
                print(f"   ✅ fd is available: {fd.get_version()}")

            # Test 2: Basic fd search
            print("\n2. Testing basic fd search...")
            try:
                # Use glob mode for the *.py pattern
                files = fd.find(pattern="*.py", path=".", max_results=5, use_glob=True)
                print(f"   ✅ Found {len(files)} Python files: {files[:3]}{'...' if len(files) > 3 else ''}")
                assert isinstance(files, list)
                assert len(files) > 0
            except Exception as e:
                pytest.fail(f"fd search failed: {e}")

            # Test 3: FdFinder interface
            print("\n3. Testing FdFinder interface...")
            try:
                searcher = FdFinder()
                if searcher.is_available():
                    python_files = searcher.find_by_extension(".py", max_depth=2)
                    print(f"   ✅ FdFinder found {len(python_files)} Python files")
                    assert isinstance(python_files, list)
                else:
                    pytest.skip("FdFinder (fd) not available")
            except Exception as e:
                pytest.fail(f"FdFinder failed: {e}")

            # Test 4: DirectoryProfiler with fd backend
            print("\n4. Testing DirectoryProfiler with fd backend...")
            try:
                profiler = DirectoryProfiler(search_backend="fd")
                if not profiler.is_fd_available():
                    pytest.skip("DirectoryProfiler fd backend not available")

                print("   ✅ DirectoryProfiler fd backend available")

                # Quick test on current directory
                result = profiler.probe(".", max_depth=2)
                print(f"   ✅ Analysis completed: {result['summary']['total_files']} files found")
                print(f"   ✅ Backend used: {result['timing']['implementation']}")
                assert "summary" in result and "total_files" in result["summary"]
                assert result["summary"]["total_files"] >= 0
                assert "timing" in result and "implementation" in result["timing"]
            except Exception as e:
                pytest.fail(f"DirectoryProfiler fd backend failed: {e}")

    def test_backend_comparison():
        """Compare different backends."""
        print("\n🔬 Backend Performance Comparison\n")

        import time

        test_dir = "."
        max_depth = 2

        backends = []

        # Test available backends
        for backend in ["python", "rust", "fd"]:
            try:
                profiler = DirectoryProfiler(search_backend=backend)

                # Check if backend is actually available
                if backend == "fd" and not profiler.is_fd_available():
                    continue
                elif backend == "rust" and not profiler.is_rust_available():
                    continue

                print(f"Testing {backend} backend...")
                start_time = time.time()
                if backend == "rust":
                    # Suppress the progress warning here so the dedicated warning test can assert it
                    with warnings.catch_warnings():
                        warnings.filterwarnings("ignore", message=WARNING_REGEX)
                        result = profiler.probe(test_dir, max_depth=max_depth)
                else:
                    result = profiler.probe(test_dir, max_depth=max_depth)
                elapsed = time.time() - start_time

                backends.append(
                    {
                        "name": backend,
                        "time": elapsed,
                        "files": result["summary"]["total_files"],
                        "folders": result["summary"]["total_folders"],
                    }
                )

                print(f"   {backend}: {elapsed:.3f}s, {result['summary']['total_files']} files")

            except Exception as e:
                print(f"   {backend}: Failed - {e}")

        # Show comparison
        if backends:
            print("\n📊 Results Summary:")
            fastest = min(backends, key=lambda x: x["time"])
            for backend in backends:
                speedup = fastest["time"] / backend["time"]
                if backend == fastest:
                    print(f"   🏆 {backend['name']}: {backend['time']:.3f}s (fastest)")
                else:
                    print(f"   📈 {backend['name']}: {backend['time']:.3f}s ({speedup:.1f}x slower)")

    def test_fd_finder_features():
        """Test FdFinder advanced features."""

        searcher = FdFinder()
        if not searcher.is_available():
            print("❌ fd not available for advanced testing")
            return

        # Test different search types
        tests = [
            ("Python files", lambda: searcher.find_by_extension(".py")),
            ("Recent files (1d)", lambda: searcher.find_recent_files(changed_within="1d")),
            ("Large files (>1k)", lambda: searcher.find_large_files(min_size="1k")),
            ("Empty directories", lambda: searcher.find_empty_directories()),
            ("File count", lambda: searcher.count_files()),
        ]

        for test_name, test_func in tests:
            try:
                result = test_func()
                if isinstance(result, int):
                    print(f"✅ {test_name}: {result}")
                else:
                    print(f"✅ {test_name}: {len(result)} results")
            except Exception as e:
                print(f"❌ {test_name}: Failed - {e}")

    def test_rust_progress_warning_expected():
        """Ensure the Rust progress warning is emitted (if Rust backend is used)."""
        if not RUST_AVAILABLE_LOCAL:
            pytest.skip("Rust backend not available")

        # The profiler emits an informational UserWarning about limited progress updates.
        with pytest.warns(UserWarning, match=WARNING_REGEX):
            profiler = DirectoryProfiler(search_backend="rust")
            _ = profiler.probe(".", max_depth=2)

    def test_rust_progress_warning_suppressed():
        """Run the same profiler probe while explicitly suppressing the progress warning."""
        if not RUST_AVAILABLE_LOCAL:
            pytest.skip("Rust backend not available")

        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=WARNING_REGEX)
            profiler = DirectoryProfiler(search_backend="rust")
            _ = profiler.probe(".", max_depth=2)

    if __name__ == "__main__":
        print("🚀 filoma fd Integration Test\n")

        # Run main smoke test
        test_fd_integration()
