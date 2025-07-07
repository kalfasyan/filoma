#!/usr/bin/env python3
"""
Test script for the new parallel implementation
"""
import sys
import tempfile
import time
from pathlib import Path

# Add the src directory to the path so we can import filoma
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def create_test_structure(base_path: Path, num_dirs: int = 50, num_files_per_dir: int = 20):
    """Create a test directory structure."""
    print(f"Creating test structure with {num_dirs} directories and {num_files_per_dir} files each...")

    for i in range(num_dirs):
        dir_path = base_path / f"test_dir_{i:03d}"
        dir_path.mkdir(exist_ok=True)

        for j in range(num_files_per_dir):
            file_path = dir_path / f"file_{j:03d}.{['txt', 'py', 'rs', 'md', 'json'][j % 5]}"
            file_path.write_text(f"Test content for file {j} in directory {i}")

    print(f"✅ Created {num_dirs} directories with {num_dirs * num_files_per_dir} total files")

def test_implementation(profiler, test_path: str, name: str):
    """Test a single implementation."""
    print(f"\n🔥 Testing {name} implementation...")

    start_time = time.time()
    try:
        result = profiler.analyze(test_path)
        end_time = time.time()

        elapsed = end_time - start_time
        total_files = result["summary"]["total_files"]
        total_folders = result["summary"]["total_folders"]

        print(f"⏱️  {name}: {elapsed:.3f}s")
        print(f"📁 Found {total_folders} folders, {total_files} files")
        print(f"🚀 Performance: {total_files / elapsed:.0f} files/second")

        return elapsed, total_files
    except Exception as e:
        print(f"❌ Error with {name}: {e}")
        return None, None

def main():
    try:
        from filoma.directories import DirectoryProfiler
        print("✅ Successfully imported DirectoryProfiler")
    except ImportError as e:
        print(f"❌ Could not import DirectoryProfiler: {e}")
        return

    with tempfile.TemporaryDirectory() as temp_dir:
        test_path = Path(temp_dir) / "parallel_test"
        test_path.mkdir()

        # Create test structure
        create_test_structure(test_path, num_dirs=100, num_files_per_dir=50)

        print(f"\n📊 Starting tests on {test_path}")
        print("=" * 80)

        # Test Python implementation
        python_profiler = DirectoryProfiler(use_rust=False)
        python_time, file_count = test_implementation(python_profiler, str(test_path), "Python")

        # Test Sequential Rust implementation
        rust_sequential_profiler = DirectoryProfiler(use_rust=True, use_parallel=False)
        print(f"\nRust available: {rust_sequential_profiler.is_rust_available()}")

        if rust_sequential_profiler.is_rust_available():
            rust_seq_time, _ = test_implementation(rust_sequential_profiler, str(test_path), "Rust Sequential")
        else:
            rust_seq_time = None

        # Test Parallel Rust implementation
        rust_parallel_profiler = DirectoryProfiler(use_rust=True, use_parallel=True, parallel_threshold=100)
        print(f"Parallel available: {rust_parallel_profiler.is_parallel_available()}")

        if rust_parallel_profiler.is_parallel_available():
            rust_par_time, _ = test_implementation(rust_parallel_profiler, str(test_path), "Rust Parallel")
        else:
            rust_par_time = None
            print("\n⚠️  Rust parallel implementation not available")

        # Show comparison results
        print("\n🎯 Performance Comparison:")
        print("=" * 50)
        if python_time:
            print(f"   Python:           {python_time:.3f}s")

        if rust_seq_time and python_time:
            seq_speedup = python_time / rust_seq_time
            print(f"   Rust Sequential:  {rust_seq_time:.3f}s ({seq_speedup:.1f}x faster)")

        if rust_par_time and python_time:
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
