#!/usr/bin/env python3
"""
Test script for fd integration in filoma.

This script tests the new fd integration capabilities.
"""

import sys
from pathlib import Path

# Add src to path so we can import filoma
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from filoma.core import FdIntegration
from filoma.directories import DirectoryProfiler, FdSearcher


def test_fd_integration():
    """Test fd integration components."""
    print("🔍 Testing fd Integration\n")

    # Test 1: Check fd availability
    print("1. Checking fd availability...")
    fd = FdIntegration()
    if fd.is_available():
        print(f"   ✅ fd is available: {fd.get_version()}")
    else:
        print("   ❌ fd not available")
        return False

    # Test 2: Basic fd search
    print("\n2. Testing basic fd search...")
    try:
        # Use glob mode for the *.py pattern
        files = fd.search(pattern="*.py", base_path=".", max_results=5, use_glob=True)
        print(f"   ✅ Found {len(files)} Python files: {files[:3]}{'...' if len(files) > 3 else ''}")
    except Exception as e:
        print(f"   ❌ fd search failed: {e}")
        return False

    # Test 3: FdSearcher interface
    print("\n3. Testing FdSearcher interface...")
    try:
        searcher = FdSearcher()
        if searcher.is_available():
            python_files = searcher.find_by_extension(".py", max_depth=2)
            print(f"   ✅ FdSearcher found {len(python_files)} Python files")
        else:
            print("   ❌ FdSearcher not available")
    except Exception as e:
        print(f"   ❌ FdSearcher failed: {e}")

    # Test 4: DirectoryProfiler with fd backend
    print("\n4. Testing DirectoryProfiler with fd backend...")
    try:
        profiler = DirectoryProfiler(search_backend="fd")
        if profiler.is_fd_available():
            print("   ✅ DirectoryProfiler fd backend available")

            # Quick test on current directory
            result = profiler.analyze(".", max_depth=2)
            print(f"   ✅ Analysis completed: {result['summary']['total_files']} files found")
            print(f"   ✅ Backend used: {result['timing']['implementation']}")
        else:
            print("   ❌ DirectoryProfiler fd backend not available")
    except Exception as e:
        print(f"   ❌ DirectoryProfiler fd backend failed: {e}")

    return True


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
            result = profiler.analyze(test_dir, max_depth=max_depth)
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


def test_fd_searcher_features():
    """Test FdSearcher advanced features."""
    print("\n🛠️  Testing FdSearcher Advanced Features\n")

    searcher = FdSearcher()
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


if __name__ == "__main__":
    print("🚀 filoma fd Integration Test\n")

    success = test_fd_integration()

    if success:
        test_backend_comparison()
        test_fd_searcher_features()
        print("\n🎉 All tests completed!")
    else:
        print("\n💥 Basic fd integration tests failed")
        sys.exit(1)
