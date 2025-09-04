#!/usr/bin/env python3
"""
Comprehensive test comparing DataFrame functionality between Python and Rust implementations.
"""

import sys
import time
from pathlib import Path

# Add the src directory to the path so we can import filoma
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from filoma.directories.directory_profiler import DirectoryProfiler


def compare_implementations():
    """Compare DataFrame functionality between Python and Rust implementations."""

    current_dir = str(Path(__file__).parent.parent.parent)  # Go to repo root

    print("=== DataFrame Functionality Comparison ===\n")

    # Test Python implementation
    print("🐍 Testing Python implementation...")
    profiler_python = DirectoryProfiler(use_rust=False, build_dataframe=True)

    start_time = time.time()
    analysis_python = profiler_python.probe(current_dir, max_depth=2)
    python_time = time.time() - start_time

    df_python = profiler_python.get_dataframe(analysis_python)
    print(f"   ✅ Python: {len(df_python)} rows, {python_time:.3f}s")

    # Test Rust implementation
    print("🦀 Testing Rust implementation...")
    profiler_rust = DirectoryProfiler(use_rust=True, build_dataframe=True)

    start_time = time.time()
    analysis_rust = profiler_rust.probe(current_dir, max_depth=2)
    rust_time = time.time() - start_time

    df_rust = profiler_rust.get_dataframe(analysis_rust)
    print(f"   ✅ Rust: {len(df_rust)} rows, {rust_time:.3f}s")

    # Compare results
    print("\n📊 Performance comparison:")
    print(f"   Python: {python_time:.3f}s")
    print(f"   Rust:   {rust_time:.3f}s")
    if rust_time > 0:
        speedup = python_time / rust_time
        print(f"   Speedup: {speedup:.1f}x {'🚀' if speedup > 1 else '🐌'}")

    print("\n📋 Results comparison:")
    print(f"   Python DataFrame: {len(df_python)} rows")
    print(f"   Rust DataFrame:   {len(df_rust)} rows")
    print(f"   Same row count: {'✅' if len(df_python) == len(df_rust) else '❌'}")

    # Test DataFrame functionality on both
    print("\n🔧 Testing DataFrame methods:")

    # Python extensions
    py_extensions = df_python.group_by_extension()
    print(f"   Python extensions: {len(py_extensions)} unique")

    # Rust extensions
    rust_extensions = df_rust.group_by_extension()
    print(f"   Rust extensions:   {len(rust_extensions)} unique")

    # Compare Python files
    py_files_python = df_python.filter_by_extension(".py")
    py_files_rust = df_rust.filter_by_extension(".py")
    print(f"   Python files (Python impl): {len(py_files_python)}")
    print(f"   Python files (Rust impl):   {len(py_files_rust)}")
    print(f"   Same Python file count: {'✅' if len(py_files_python) == len(py_files_rust) else '❌'}")

    print("\n🎯 Both implementations now support DataFrame functionality!")
    print("   The Rust implementation gets the speed benefits for statistics,")
    print("   while file path collection uses Python for DataFrame building.")


if __name__ == "__main__":
    compare_implementations()
