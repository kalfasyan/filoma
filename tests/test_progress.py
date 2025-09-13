#!/usr/bin/env python3
"""
Test script to demonstrate the new progress indication and timing features
for the directory profiler.
"""

import os
import tempfile
from pathlib import Path

import pytest

from filoma.directories import DirectoryProfiler, DirectoryProfilerConfig

# Skip on CI where external tools like `fd` may be missing
CI = os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true"
pytestmark = pytest.mark.skipif(CI, reason="Skip on CI where fd may be unavailable")


def test_progress_features():
    """Test the new progress and timing features."""
    print("=" * 80)
    print("Testing Directory Profiler with Progress and Timing")
    print("=" * 80)
    # Use a small temporary directory to avoid scanning the full repo.
    import tempfile

    test_dir = Path(tempfile.mkdtemp())
    configs = [
        {"name": "Python Implementation with Progress", "use_rust": False, "show_progress": True},
        {"name": "Rust Sequential with Progress", "use_rust": True, "use_parallel": False, "show_progress": True},
        {"name": "Rust Parallel with Progress", "use_rust": True, "use_parallel": True, "show_progress": True},
        {"name": "Python Implementation without Progress", "use_rust": False, "show_progress": False},
    ]

    for config in configs:
        print(f"\n🔍 Testing: {config['name']}")
        print("-" * 50)
        profiler_cfg = DirectoryProfilerConfig(
            use_rust=config.get("use_rust", True),
            use_parallel=config.get("use_parallel", True),
            show_progress=config.get("show_progress", True),
            build_dataframe=False,
        )
        profiler = DirectoryProfiler(profiler_cfg)
        impl_info = profiler.get_implementation_info()
        print(f"Implementation: {impl_info}")
        try:
            # Limit max_depth to 1 and avoid heavy filesystem traversal.
            result = profiler.probe(str(test_dir), max_depth=1)
            profiler.print_summary(result)
            if "timing" in result:
                timing = result["timing"]
                print("⏱️  Timing Details:")
                print(f"   - Elapsed: {timing['elapsed_seconds']:.3f}s")
                print(f"   - Implementation: {timing['implementation']}")
                print(f"   - Speed: {timing['items_per_second']:,.0f} items/sec")
        except Exception as e:
            print(f"❌ Error: {e}")
    # Keep loop tight; no artificial sleep
    pass


def test_custom_progress_callback():
    """Test custom progress callback functionality."""
    print("\n🔄 Testing Custom Progress Callback")
    print("-" * 50)

    def custom_callback(message: str, current: int, total: int):
        if total > 0:
            percentage = (current / total) * 100
            print(f"📊 {message} - {current:,}/{total:,} ({percentage:.1f}%)")
        else:
            print(f"📊 {message} - {current:,} items processed")

    profiler_cfg = DirectoryProfilerConfig(use_rust=False, show_progress=False, progress_callback=custom_callback)
    profiler = DirectoryProfiler(profiler_cfg)
    # Use a tiny tempdir for callback test
    tmp = Path(tempfile.mkdtemp())
    (tmp / "file.txt").write_text("x")
    test_dir = tmp
    result = profiler.probe(str(test_dir), max_depth=1)
    print("✅ Custom callback test completed!")
    print(f"   - Found {result['summary']['total_files']} files")
    print(f"   - Found {result['summary']['total_folders']} folders")


def test_large_directory():
    """Test with a larger directory to better see progress indication."""
    print("\n" + "=" * 60)
    print("BONUS TEST: Large Directory Structure")
    print("=" * 60)
    # large directory test intentionally omitted for speed in CI; kept as a
    # commented-out option for local profiling if needed.


if __name__ == "__main__":
    test_progress_features()
    test_custom_progress_callback()
    # Uncomment to run the large directory test
    # test_large_directory()
