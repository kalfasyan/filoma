#!/usr/bin/env python3
"""
Benchmark script to compare Python vs Rust implementation performance
"""

import tempfile
import time
from pathlib import Path


# Create a test directory structure
def create_test_structure(base_path: Path, num_dirs: int = 100, num_files_per_dir: int = 50):
    """Create a test directory structure for benchmarking."""
    print(f"Creating test structure with {num_dirs} directories and {num_files_per_dir} files each...")

    for i in range(num_dirs):
        dir_path = base_path / f"test_dir_{i:03d}"
        dir_path.mkdir(exist_ok=True)

        for j in range(num_files_per_dir):
            file_path = dir_path / f"file_{j:03d}.{['txt', 'py', 'rs', 'md', 'json'][j % 5]}"
            file_path.write_text(f"Test content for file {j} in directory {i}")

    print(f"✅ Created {num_dirs} directories with {num_dirs * num_files_per_dir} total files")


def benchmark_implementation(analyzer, test_path: str, name: str):
    """Benchmark a single implementation."""
    print(f"\n🔥 Benchmarking {name} implementation...")

    start_time = time.time()
    result = analyzer.analyze(test_path)
    end_time = time.time()

    elapsed = end_time - start_time
    total_files = result["summary"]["total_files"]
    total_folders = result["summary"]["total_folders"]

    print(f"⏱️  {name}: {elapsed:.3f}s")
    print(f"📁 Found {total_folders} folders, {total_files} files")
    print(f"🚀 Performance: {total_files / elapsed:.0f} files/second")

    return elapsed, total_files


def main():
    # Import after potential building
    try:
        from filoma.dir import DirectoryAnalyzer
    except ImportError:
        print("❌ Could not import DirectoryAnalyzer. Make sure filoma is installed.")
        return

    with tempfile.TemporaryDirectory() as temp_dir:
        test_path = Path(temp_dir) / "benchmark_test"
        test_path.mkdir()

        # Create test structure
        create_test_structure(test_path, num_dirs=500, num_files_per_dir=200)

        print(f"\n📊 Starting benchmark on {test_path}")
        print("=" * 60)

        # Test Python implementation
        python_analyzer = DirectoryAnalyzer(use_rust=False)
        python_time, file_count = benchmark_implementation(python_analyzer, str(test_path), "Python")

        # Test Rust implementation (if available)
        rust_analyzer = DirectoryAnalyzer(use_rust=True)
        if rust_analyzer.use_rust:
            rust_time, _ = benchmark_implementation(rust_analyzer, str(test_path), "Rust")

            speedup = python_time / rust_time
            print("\n🎯 Results:")
            print(f"   Python: {python_time:.3f}s")
            print(f"   Rust:   {rust_time:.3f}s")
            print(f"   Speedup: {speedup:.1f}x faster with Rust! 🚀")
        else:
            print("\n⚠️  Rust implementation not available, only Python tested")


if __name__ == "__main__":
    main()
