#!/usr/bin/env python3
"""
Test script to see how DataFrame works with Rust acceleration.
"""

import sys
from pathlib import Path

# Add the src directory to the path so we can import filoma
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from filoma.directories.directory_profiler import DirectoryProfiler


def test_rust_with_dataframe():
    """Test DataFrame functionality with Rust enabled."""

    # Test with Rust + DataFrame
    profiler_rust = DirectoryProfiler(use_rust=True, build_dataframe=True)

    print(f"Implementation info: {profiler_rust.get_implementation_info()}")
    print(f"Using Rust: {profiler_rust.is_rust_available()}")
    print(f"DataFrame enabled: {profiler_rust.is_dataframe_enabled()}")

    # Analyze current directory
    current_dir = str(Path(__file__).parent.parent.parent)  # Go to repo root
    analysis = profiler_rust.probe(current_dir, max_depth=1)

    # Check if DataFrame was created
    df = profiler_rust.get_dataframe(analysis)
    if df is not None:
        print(f"✅ DataFrame created with Rust: {len(df)} rows")
    else:
        print("❌ No DataFrame created with Rust")

    print(f"Analysis keys: {list(analysis.keys())}")


if __name__ == "__main__":
    test_rust_with_dataframe()
