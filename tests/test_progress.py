#!/usr/bin/env python3
"""
Test script to demonstrate the new progress indication and timing features
for the directory profiler.
"""

import os
import tempfile
import time
from pathlib import Path

import pytest

from filoma.directories import DirectoryProfiler

# Skip on CI where external tools like `fd` may be missing
CI = os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true"
pytestmark = pytest.mark.skipif(CI, reason="Skip on CI where fd may be unavailable")

# Use print instead of logger for standalone test script


def test_progress_features():
    """Test the new progress and timing features."""
    print("=" * 80)
    print("Testing Directory Profiler with Progress and Timing")
    print("=" * 80)
    test_dir = Path.cwd()
    configs = [
        {
            "name": "Python Implementation with Progress",
            "use_rust": False,
            "show_progress": True,
        },
        {
            "name": "Rust Sequential with Progress",
            "use_rust": True,
            "use_parallel": False,
            "show_progress": True,
        },
        {
            "name": "Rust Parallel with Progress",
            "use_rust": True,
            "use_parallel": True,
            "show_progress": True,
        },
        {
            "name": "Python Implementation without Progress",
            "use_rust": False,
            "show_progress": False,
        },
    ]
    for config in configs:
        print(f"\n🔍 Testing: {config['name']}")
        print("-" * 50)
        profiler = DirectoryProfiler(
            use_rust=config.get("use_rust", True),
            use_parallel=config.get("use_parallel", True),
            show_progress=config.get("show_progress", True),
            build_dataframe=False,
        )
        impl_info = profiler.get_implementation_info()
        print(f"Implementation: {impl_info}")
        try:
            result = profiler.probe(str(test_dir), max_depth=2)
            profiler.print_summary(result)
            if "timing" in result:
                timing = result["timing"]
                print("⏱️  Timing Details:")
                print(f"   - Elapsed: {timing['elapsed_seconds']:.3f}s")
                print(f"   - Implementation: {timing['implementation']}")
                print(f"   - Speed: {timing['items_per_second']:,.0f} items/sec")
        except Exception as e:
            print(f"❌ Error: {e}")
        print("\n" + "=" * 50)
        time.sleep(0.5)


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

    profiler = DirectoryProfiler(use_rust=False, show_progress=False, progress_callback=custom_callback)
    test_dir = Path.cwd()
    result = profiler.probe(str(test_dir), max_depth=1)
    print("✅ Custom callback test completed!")
    print(f"   - Found {result['summary']['total_files']} files")
    print(f"   - Found {result['summary']['total_folders']} folders")


def test_large_directory():
    """Test with a larger directory to better see progress indication."""
    print("\n" + "=" * 60)
    print("BONUS TEST: Large Directory Structure")
    print("=" * 60)
    with tempfile.TemporaryDirectory() as temp_dir:
        print(f"Creating test directory structure in {temp_dir}")
        for i in range(5):
            level_dir = Path(temp_dir) / f"level_{i}"
            level_dir.mkdir()
            for j in range(20):
                sub_dir = level_dir / f"subdir_{j}"
                sub_dir.mkdir()
                for k in range(10):
                    file_path = sub_dir / f"file_{k}.txt"
                    file_path.write_text(f"Content of file {k} in {sub_dir}")
        print("Test directory structure created. Starting analysis...")
        profiler = DirectoryProfiler(use_rust=True, use_parallel=True, show_progress=True, build_dataframe=False)
        result = profiler.probe(temp_dir)
        profiler.print_summary(result)


if __name__ == "__main__":
    test_progress_features()
    test_custom_progress_callback()
    # Uncomment to run the large directory test
    # test_large_directory()
