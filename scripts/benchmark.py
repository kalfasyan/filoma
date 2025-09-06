#!/usr/bin/env python3
"""
Benchmark script to compare Python vs Rust implementation performance
"""

import tempfile
import time
from pathlib import Path


# Create a test directory structure
def create_test_structure(path: Path, num_dirs: int = 100, num_files_per_dir: int = 50):
    """Create a test directory structure for benchmarking."""
    print(f"Creating test structure with {num_dirs} directories and {num_files_per_dir} files each...")

    for i in range(num_dirs):
        dir_path = path / f"test_dir_{i:03d}"
        dir_path.mkdir(parents=True, exist_ok=True)

        for j in range(num_files_per_dir):
            file_path = dir_path / f"file_{j:03d}.{['txt', 'py', 'rs', 'md', 'json'][j % 5]}"
            file_path.write_text(f"Test content for file {j} in directory {i}")

    print(f"✅ Created {num_dirs} directories with {num_dirs * num_files_per_dir} total files")


def benchmark_implementation(profiler, test_path: str, name: str):
    """Benchmark a single implementation."""
    print(f"\n🔥 Benchmarking {name} implementation...")

    start_time = time.time()
    result = profiler.probe(test_path)
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
        from filoma.directories import DirectoryProfiler
    except ImportError:
        print("❌ Could not import DirectoryProfiler. Make sure filoma is installed.")
        return

    with tempfile.TemporaryDirectory() as temp_dir:
        test_path = Path(temp_dir) / "benchmark_test"
        test_path.mkdir()

        # Create test structure - larger for better parallel testing
        create_test_structure(test_path, num_dirs=1000, num_files_per_dir=100)

        print(f"\n📊 Starting benchmark on {test_path}")
        print("=" * 80)

        # Test Python implementation
        python_profiler = DirectoryProfiler(use_rust=False)
        python_time, file_count = benchmark_implementation(python_profiler, str(test_path), "Python")

        # Test Sequential Rust implementation
        rust_sequential_profiler = DirectoryProfiler(use_rust=True, use_parallel=False)
        if rust_sequential_profiler.is_rust_available():
            rust_seq_time, _ = benchmark_implementation(rust_sequential_profiler, str(test_path), "Rust Sequential")
        else:
            rust_seq_time = None

        # Test Parallel Rust implementation
        rust_parallel_profiler = DirectoryProfiler(use_rust=True, use_parallel=True, parallel_threshold=500)
        if rust_parallel_profiler.is_parallel_available():
            rust_par_time, _ = benchmark_implementation(rust_parallel_profiler, str(test_path), "Rust Parallel")
        else:
            rust_par_time = None
            print("\n⚠️  Rust parallel implementation not available")

        # Show comparison results
        print("\n🎯 Performance Comparison:")
        print("=" * 50)
        print(f"   Python:           {python_time:.3f}s")

        if rust_seq_time:
            seq_speedup = python_time / rust_seq_time
            print(f"   Rust Sequential:  {rust_seq_time:.3f}s ({seq_speedup:.1f}x faster)")

        if rust_par_time:
            par_speedup = python_time / rust_par_time
            print(f"   Rust Parallel:    {rust_par_time:.3f}s ({par_speedup:.1f}x faster)")

            if rust_seq_time:
                par_vs_seq = rust_seq_time / rust_par_time
                print(f"   Parallel vs Sequential: {par_vs_seq:.1f}x faster")

        # Show implementation info
        if rust_parallel_profiler.is_rust_available():
            impl_info = rust_parallel_profiler.get_implementation_info()
            print("\n📋 Implementation Status:")
            print(f"   Rust Available: {'✅' if impl_info['rust_available'] else '❌'}")
            print(f"   Parallel Available: {'✅' if impl_info['rust_parallel_available'] else '❌'}")


if __name__ == "__main__":
    main()
