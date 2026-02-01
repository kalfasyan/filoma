#!/usr/bin/env python3
"""Benchmark script comparing filoma vs os.walk vs pathlib.

This script creates realistic benchmarks comparing:
- os.walk (standard library)
- pathlib.Path.rglob (modern Python)
- filoma with different backends (Rust, fd, Python)

It ensures "cold cache" conditions by clearing filesystem cache between runs.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from filoma.directories import DirectoryProfiler, DirectoryProfilerConfig
except ImportError:
    print("❌ filoma not installed. Install with: pip install filoma")
    sys.exit(1)


def clear_filesystem_cache() -> None:
    """Clear OS filesystem cache to ensure cold cache conditions.

    This requires root privileges. If not available, prints a warning
    but continues (results may be affected by caching).
    """
    try:
        # Sync filesystem buffers
        subprocess.run(["sync"], check=True, capture_output=True)

        # Clear page cache, dentries, and inodes
        # Requires root/sudo access
        result = subprocess.run(
            ["sudo", "tee", "/proc/sys/vm/drop_caches"], input="3\n", text=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=False
        )

        if result.returncode != 0:
            print("⚠️  Warning: Could not clear filesystem cache (requires sudo).")
            print("   Results may be affected by OS caching.")
            print("   Run with sudo for accurate cold-cache benchmarks.")

        # Give the system a moment to settle
        time.sleep(0.5)

    except FileNotFoundError:
        # Windows or system without these commands
        print("⚠️  Warning: Cannot clear filesystem cache on this system.")
        print("   Results may be affected by OS caching.")
    except Exception as e:
        print(f"⚠️  Warning: Error clearing cache: {e}")
        print("   Results may be affected by OS caching.")


def create_test_structure(
    base_path: Path, num_dirs: int = 100, num_files_per_dir: int = 50, max_depth: int = 3, seed: Optional[int] = None
) -> Tuple[int, int]:
    """Create a test directory structure for benchmarking.

    Args:
        base_path: Base directory to create structure in
        num_dirs: Number of directories to create per level
        num_files_per_dir: Number of files per directory
        max_depth: Maximum directory depth
        seed: Random seed for reproducible structures

    Returns:
        Tuple of (total_files, total_dirs) created

    """
    import random

    if seed is not None:
        random.seed(seed)

    extensions = ["txt", "py", "md", "json", "yaml", "csv", "log", "dat"]

    total_files = 0
    total_dirs = 0

    def create_level(parent: Path, depth: int, dirs_at_level: int):
        nonlocal total_files, total_dirs

        if depth > max_depth:
            return

        for i in range(dirs_at_level):
            dir_name = f"dir_{depth}_{i:04d}"
            dir_path = parent / dir_name
            dir_path.mkdir(parents=True, exist_ok=True)
            total_dirs += 1

            # Create files in this directory
            for j in range(num_files_per_dir):
                ext = random.choice(extensions)
                file_path = dir_path / f"file_{j:04d}.{ext}"
                # Write some content to make files realistic
                file_path.write_text(f"Test content for {file_path.name}\n" * 10)
                total_files += 1

            # Recursively create subdirectories
            if depth < max_depth:
                subdirs = random.randint(0, num_dirs // 10)  # Fewer subdirs
                create_level(dir_path, depth + 1, subdirs)

    create_level(base_path, 0, num_dirs)

    return total_files, total_dirs


def benchmark_os_walk(path: str) -> Tuple[float, int, int]:
    """Benchmark using os.walk (standard library).

    Returns:
        Tuple of (elapsed_time, file_count, dir_count)

    """
    file_count = 0
    dir_count = 0

    start = time.perf_counter()
    for root, dirs, files in os.walk(path):
        dir_count += len(dirs)
        file_count += len(files)
    elapsed = time.perf_counter() - start

    return elapsed, file_count, dir_count


def benchmark_pathlib_rglob(path: str) -> Tuple[float, int, int]:
    """Benchmark using pathlib.Path.rglob.

    Returns:
        Tuple of (elapsed_time, file_count, dir_count)

    """
    from pathlib import Path

    p = Path(path)
    file_count = 0
    dir_count = 0

    start = time.perf_counter()
    # Count files
    for item in p.rglob("*"):
        if item.is_file():
            file_count += 1
        elif item.is_dir():
            dir_count += 1
    elapsed = time.perf_counter() - start

    return elapsed, file_count, dir_count


def benchmark_filoma(path: str, backend: str = "auto", fast_path_only: bool = False) -> Optional[Tuple[float, int, int]]:
    """Benchmark using filoma with specified backend.

    Args:
        path: Path to scan
        backend: Backend to use ('rust', 'fd', 'python', or 'auto')
        fast_path_only: If True, only collect paths (no metadata)

    Returns:
        Tuple of (elapsed_time, file_count, dir_count) or None if backend unavailable

    """
    try:
        config = DirectoryProfilerConfig(search_backend=backend, fast_path_only=fast_path_only, show_progress=False)
        profiler = DirectoryProfiler(config)

        # Check if backend is available
        if backend == "rust" and not profiler.is_rust_available():
            return None
        if backend == "fd" and not profiler.is_fd_available():
            return None

        start = time.perf_counter()
        result = profiler.probe(path)
        elapsed = time.perf_counter() - start

        summary = result["summary"]
        file_count = summary["total_files"]
        dir_count = summary["total_folders"]

        return elapsed, file_count, dir_count

    except Exception as e:
        print(f"   Error benchmarking filoma ({backend}): {e}")
        return None


def run_benchmark_suite(test_path: str, iterations: int = 3, clear_cache: bool = True) -> Tuple[Dict[str, List[float]], Dict[str, Tuple[int, int]]]:
    """Run a complete benchmark suite.

    Args:
        test_path: Path to benchmark
        iterations: Number of iterations per method
        clear_cache: Whether to clear filesystem cache between runs

    Returns:
        Tuple of (results dict mapping method names to elapsed times,
                  file_counts dict mapping method names to (files, dirs))

    """
    results: Dict[str, List[float]] = {}
    file_counts: Dict[str, Tuple[int, int]] = {}

    methods = [
        ("os.walk", lambda: benchmark_os_walk(test_path)),
        ("pathlib.rglob", lambda: benchmark_pathlib_rglob(test_path)),
        ("filoma (auto)", lambda: benchmark_filoma(test_path, "auto")),
        ("filoma (rust)", lambda: benchmark_filoma(test_path, "rust")),
        ("filoma (fd)", lambda: benchmark_filoma(test_path, "fd")),
        ("filoma (python)", lambda: benchmark_filoma(test_path, "python")),
    ]

    print(f"\n📊 Running benchmark suite ({iterations} iterations each)")
    print("=" * 80)

    for method_name, method_func in methods:
        print(f"\n🔄 Benchmarking {method_name}...")
        times = []

        for i in range(iterations):
            if clear_cache and i > 0:  # Don't clear before first run
                clear_filesystem_cache()

            result = method_func()
            if result is None:
                if i == 0:  # Only print warning on first iteration
                    print(f"   ⚠️  {method_name} not available, skipping")
                break

            elapsed, file_count, dir_count = result
            times.append(elapsed)

            if i == 0:
                file_counts[method_name] = (file_count, dir_count)
                print(f"   Iteration {i + 1}: {elapsed:.3f}s ({file_count} files, {dir_count} dirs)")
            else:
                print(f"   Iteration {i + 1}: {elapsed:.3f}s")

        if times:
            results[method_name] = times
            avg_time = sum(times) / len(times)
            print(f"   ✅ Average: {avg_time:.3f}s")

    return results, file_counts


def print_results_summary(results: Dict[str, List[float]], file_counts: Dict[str, Tuple[int, int]], test_path: str):
    """Print a formatted summary of benchmark results."""
    if not results:
        print("\n❌ No results to display")
        return

    # Calculate averages
    avg_results = {name: sum(times) / len(times) for name, times in results.items()}

    # Find baseline (os.walk)
    baseline_time = avg_results.get("os.walk", None)

    print("\n" + "=" * 80)
    print("📈 BENCHMARK RESULTS SUMMARY")
    print("=" * 80)
    print(f"Test directory: {test_path}")
    print()

    # Sort by time
    sorted_results = sorted(avg_results.items(), key=lambda x: x[1])

    print(f"{'Method':<25} {'Avg Time':<12} {'Files/sec':<12} {'Speedup':<10}")
    print("-" * 80)

    for method_name, avg_time in sorted_results:
        # Calculate files/sec
        files_per_sec = "N/A"
        if method_name in file_counts:
            file_count, _ = file_counts[method_name]
            files_per_sec = f"{file_count / avg_time:,.0f}"

        # Calculate speedup vs baseline
        speedup = ""
        if baseline_time and method_name != "os.walk":
            speedup_val = baseline_time / avg_time
            speedup = f"{speedup_val:.2f}x"
        elif method_name == "os.walk":
            speedup = "1.00x"

        print(f"{method_name:<25} {avg_time:>10.3f}s {files_per_sec:>12} {speedup:>10}")

    print("-" * 80)

    # Show detailed statistics
    print("\n📊 Detailed Statistics:")
    print("-" * 80)
    for method_name, times in sorted(results.items(), key=lambda x: sum(x[1]) / len(x[1])):
        avg = sum(times) / len(times)
        min_time = min(times)
        max_time = max(times)
        std_dev = (sum((t - avg) ** 2 for t in times) / len(times)) ** 0.5

        print(f"\n{method_name}:")
        print(f"  Average: {avg:.3f}s")
        print(f"  Min:     {min_time:.3f}s")
        print(f"  Max:     {max_time:.3f}s")
        print(f"  Std Dev: {std_dev:.3f}s")


def main():
    """Run the benchmark comparison."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Benchmark filoma vs os.walk vs pathlib",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Benchmark with default settings (creates temp directory)
  python benchmark_comparison.py

  # Benchmark existing directory
  python benchmark_comparison.py --path /path/to/directory

  # More iterations for better accuracy
  python benchmark_comparison.py --iterations 5

  # Skip cache clearing (faster, but less realistic)
  python benchmark_comparison.py --no-clear-cache
        """,
    )

    parser.add_argument("--path", type=str, help="Path to benchmark (creates temp directory if not specified)")
    parser.add_argument("--iterations", type=int, default=3, help="Number of iterations per method (default: 3)")
    parser.add_argument("--num-dirs", type=int, default=100, help="Number of directories per level for generated test structure (default: 100)")
    parser.add_argument("--files-per-dir", type=int, default=50, help="Number of files per directory (default: 50)")
    parser.add_argument("--max-depth", type=int, default=3, help="Maximum directory depth (default: 3)")
    parser.add_argument("--no-clear-cache", action="store_true", help="Skip filesystem cache clearing (faster but less realistic)")
    parser.add_argument("--keep-temp", action="store_true", help="Keep temporary test directory after benchmark")

    args = parser.parse_args()

    # Determine test path
    temp_dir = None
    if args.path:
        test_path = args.path
        if not os.path.exists(test_path):
            print(f"❌ Error: Path does not exist: {test_path}")
            sys.exit(1)
        print(f"📁 Using existing directory: {test_path}")
    else:
        # Create temporary test structure
        print("🔨 Creating test directory structure...")
        temp_dir = tempfile.mkdtemp(prefix="filoma_benchmark_")
        test_path = temp_dir

        print(f"   Base path: {test_path}")
        print(f"   Config: {args.num_dirs} dirs/level, {args.files_per_dir} files/dir, depth={args.max_depth}")

        files, dirs = create_test_structure(Path(test_path), num_dirs=args.num_dirs, num_files_per_dir=args.files_per_dir, max_depth=args.max_depth)

        print(f"✅ Created {files} files and {dirs} directories")

    # Run benchmarks
    try:
        results, file_counts = run_benchmark_suite(test_path, iterations=args.iterations, clear_cache=not args.no_clear_cache)

        print_results_summary(results, file_counts, test_path)

    finally:
        # Cleanup
        if temp_dir and not args.keep_temp:
            print(f"\n🧹 Cleaning up temporary directory: {temp_dir}")
            shutil.rmtree(temp_dir, ignore_errors=True)
        elif temp_dir:
            print(f"\n💾 Keeping temporary directory: {temp_dir}")


if __name__ == "__main__":
    main()
