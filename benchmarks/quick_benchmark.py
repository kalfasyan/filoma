#!/usr/bin/env python3
"""Quick benchmark script for rapid comparison testing.

This is a simplified version of benchmark_comparison.py for quick testing.
It doesn't clear cache (for speed) but provides a quick comparison.
"""

import os
import sys
import time
from pathlib import Path

try:
    from filoma.directories import DirectoryProfiler, DirectoryProfilerConfig
except ImportError:
    print("❌ filoma not installed. Install with: pip install filoma")
    sys.exit(1)


def benchmark_os_walk(path: str):
    """Benchmark os.walk."""
    file_count = 0
    dir_count = 0
    start = time.perf_counter()
    for root, dirs, files in os.walk(path):
        dir_count += len(dirs)
        file_count += len(files)
    elapsed = time.perf_counter() - start
    return elapsed, file_count, dir_count


def benchmark_pathlib(path: str):
    """Benchmark pathlib.Path.rglob."""
    p = Path(path)
    file_count = 0
    dir_count = 0
    start = time.perf_counter()
    for item in p.rglob("*"):
        if item.is_file():
            file_count += 1
        elif item.is_dir():
            dir_count += 1
    elapsed = time.perf_counter() - start
    return elapsed, file_count, dir_count


def benchmark_filoma(path: str, backend: str = "auto"):
    """Benchmark filoma."""
    try:
        config = DirectoryProfilerConfig(search_backend=backend, show_progress=False)
        profiler = DirectoryProfiler(config)

        # Check availability
        if backend == "rust" and not profiler.is_rust_available():
            return None, "Rust backend not available"
        if backend == "fd" and not profiler.is_fd_available():
            return None, "fd backend not available"

        start = time.perf_counter()
        result = profiler.probe(path)
        elapsed = time.perf_counter() - start

        summary = result["summary"]
        return elapsed, summary["total_files"], summary["total_folders"]
    except Exception as e:
        return None, str(e)


def main():
    """Run quick benchmark."""
    if len(sys.argv) < 2:
        print("Usage: python quick_benchmark.py <directory_path>")
        print("\nExample:")
        print("  python quick_benchmark.py /usr")
        print("  python quick_benchmark.py .")
        sys.exit(1)

    test_path = sys.argv[1]

    if not os.path.exists(test_path):
        print(f"❌ Error: Path does not exist: {test_path}")
        sys.exit(1)

    print(f"📊 Quick Benchmark: {test_path}")
    print("=" * 60)
    print("⚠️  Note: This uses warm cache (no cache clearing)")
    print("   For accurate cold-cache benchmarks, use benchmark_comparison.py")
    print("=" * 60)

    results = []

    # os.walk
    print("\n🔄 os.walk...")
    elapsed, files, dirs = benchmark_os_walk(test_path)
    results.append(("os.walk", elapsed, files, dirs))
    print(f"   {elapsed:.3f}s ({files} files, {dirs} dirs)")

    # pathlib
    print("\n🔄 pathlib.rglob...")
    elapsed, files, dirs = benchmark_pathlib(test_path)
    results.append(("pathlib.rglob", elapsed, files, dirs))
    print(f"   {elapsed:.3f}s ({files} files, {dirs} dirs)")

    # filoma backends
    for backend in ["auto", "rust", "fd", "python"]:
        print(f"\n🔄 filoma ({backend})...")
        result = benchmark_filoma(test_path, backend)
        if result[0] is None:
            print(f"   ⚠️  {result[1]}")
        else:
            elapsed, files, dirs = result
            results.append((f"filoma ({backend})", elapsed, files, dirs))
            print(f"   {elapsed:.3f}s ({files} files, {dirs} dirs)")

    # Summary
    if results:
        baseline = results[0][1]  # os.walk time
        print("\n" + "=" * 60)
        print("📈 Results Summary")
        print("=" * 60)
        print(f"{'Method':<20} {'Time':<12} {'Speedup':<10}")
        print("-" * 60)

        for name, elapsed, files, dirs in sorted(results, key=lambda x: x[1]):
            speedup = baseline / elapsed if elapsed > 0 else 0
            speedup_str = f"{speedup:.2f}x" if name != "os.walk" else "1.00x"
            print(f"{name:<20} {elapsed:>10.3f}s {speedup_str:>10}")


if __name__ == "__main__":
    main()
