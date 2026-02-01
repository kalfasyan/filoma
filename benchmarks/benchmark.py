#!/usr/bin/env python3
"""Unified benchmark script for filoma performance testing.

Compares filoma backends (Rust, fd, Python, async) against standard library alternatives.
Supports both local and network storage benchmarking with configurable test datasets.

Examples:
    # Quick benchmark on current directory
    python benchmarks/benchmark.py .

    # Benchmark with generated test data
    python benchmarks/benchmark.py --setup-dataset --path /tmp/bench

    # Compare local vs network storage
    python benchmarks/benchmark.py --path local=/tmp/bench --path nas=/mnt/nas --setup-dataset

    # Full benchmark with cache clearing (requires sudo)
    python benchmarks/benchmark.py --path /data --iterations 5 --clear-cache
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
import time
from multiprocessing import cpu_count
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from filoma.directories import DirectoryProfiler, DirectoryProfilerConfig
except ImportError:
    print("❌ filoma not installed. Install with: pip install filoma")
    sys.exit(1)

# Try to import the async Rust function directly for benchmarking
try:
    from filoma.filoma_core import probe_directory_rust_async

    ASYNC_AVAILABLE = True
except ImportError:
    ASYNC_AVAILABLE = False


# =============================================================================
# Test Data Generation
# =============================================================================

DATASET_SIZES = {
    "small": (10, 20),  # 200 files
    "medium": (50, 50),  # 2,500 files
    "large": (200, 100),  # 20,000 files
    "xlarge": (500, 200),  # 100,000 files
}


def create_test_structure(
    path: Path,
    num_dirs: int = 50,
    num_files_per_dir: int = 50,
    depth: int = 2,
) -> Tuple[int, int]:
    """Create a test directory structure for benchmarking.

    Args:
        path: Base directory to create structure in
        num_dirs: Number of directories at each level
        num_files_per_dir: Number of files per directory
        depth: Number of nested subdirectory levels

    Returns:
        Tuple of (total_files, total_dirs) created
    """
    extensions = ["txt", "py", "rs", "md", "json", "yaml", "csv", "log"]
    total_files = 0
    total_dirs = 0

    path.mkdir(parents=True, exist_ok=True)

    for i in range(num_dirs):
        dir_path = path / f"dir_{i:04d}"
        dir_path.mkdir(parents=True, exist_ok=True)
        total_dirs += 1

        # Create files in this directory
        for j in range(num_files_per_dir):
            ext = extensions[j % len(extensions)]
            file_path = dir_path / f"file_{j:04d}.{ext}"
            if not file_path.exists():
                file_path.write_text(f"Test content for file {j} in directory {i}\n" * 5)
            total_files += 1

        # Create nested subdirectories
        if depth > 0:
            for k in range(min(5, num_dirs // 10 or 1)):
                sub_files, sub_dirs = create_test_structure(
                    dir_path / f"sub_{k:02d}",
                    num_dirs=max(2, num_dirs // 10),
                    num_files_per_dir=max(5, num_files_per_dir // 5),
                    depth=depth - 1,
                )
                total_files += sub_files
                total_dirs += sub_dirs

    return total_files, total_dirs


# =============================================================================
# Cache Management
# =============================================================================


def clear_filesystem_cache() -> bool:
    """Clear OS filesystem cache for cold-cache benchmarking.

    Requires sudo privileges on Linux/macOS.

    Returns:
        True if cache was cleared successfully
    """
    system = platform.system()

    try:
        if system == "Linux":
            subprocess.run(["sync"], check=True)
            subprocess.run(
                ["sudo", "sh", "-c", "echo 3 > /proc/sys/vm/drop_caches"],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        elif system == "Darwin":
            subprocess.run(["sync"], check=True)
            subprocess.run(
                ["sudo", "purge"],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        else:
            print(f"⚠️  Cache clearing not supported on {system}")
            return False

        time.sleep(0.5)  # Let system settle
        return True

    except subprocess.CalledProcessError:
        print("⚠️  Failed to clear cache (requires sudo)")
        return False
    except Exception as e:
        print(f"⚠️  Error clearing cache: {e}")
        return False


# =============================================================================
# Benchmark Functions
# =============================================================================


def benchmark_os_walk(path: str) -> Tuple[float, int, int]:
    """Benchmark using os.walk (standard library)."""
    file_count = 0
    dir_count = 0

    start = time.perf_counter()
    for _root, dirs, files in os.walk(path):
        dir_count += len(dirs)
        file_count += len(files)
    elapsed = time.perf_counter() - start

    return elapsed, file_count, dir_count


def benchmark_pathlib(path: str) -> Tuple[float, int, int]:
    """Benchmark using pathlib.Path.rglob."""
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


def benchmark_filoma(
    path: str,
    backend: str,
    no_ignore: bool = False,
) -> Optional[Dict]:
    """Benchmark filoma with specified backend.

    Args:
        path: Directory path to scan
        backend: Backend to use ('rust', 'rust-seq', 'async', 'fd', 'python')
        no_ignore: Ignore .gitignore files

    Returns:
        Dict with timing and counts, or None if backend unavailable
    """
    # Special case: async backend - call Rust function directly to bypass network FS check
    if backend == "async":
        if not ASYNC_AVAILABLE:
            return {"error": "Async Rust not available"}
        try:
            start = time.perf_counter()
            result = probe_directory_rust_async(
                path,
                None,  # max_depth
                64,  # concurrency_limit
                5000,  # timeout_ms
                0,  # retries
                False,  # fast_path_only
            )
            elapsed = time.perf_counter() - start
            summary = result.get("summary", {})
            return {
                "elapsed": elapsed,
                "files": summary.get("total_files", 0),
                "dirs": summary.get("total_folders", 0),
            }
        except Exception as e:
            return {"error": str(e)}

    # Configure based on backend
    use_rust = backend in ("rust", "rust-seq")
    use_parallel = backend == "rust"
    search_backend = "fd" if backend == "fd" else ("rust" if use_rust else "python")

    # fd optimization
    fd_threads = cpu_count() if backend == "fd" else None

    try:
        config = DirectoryProfilerConfig(
            use_rust=use_rust,
            use_parallel=use_parallel,
            search_backend=search_backend,
            show_progress=False,
            fd_no_ignore=no_ignore,
            threads=fd_threads,
        )
        profiler = DirectoryProfiler(config)

        # Check availability
        if backend in ("rust", "rust-seq") and not profiler.is_rust_available():
            return {"error": "Rust not available"}
        if backend == "async" and not profiler.is_rust_available():
            return {"error": "Async Rust not available"}
        if backend == "fd" and not profiler.is_fd_available():
            return {"error": "fd not available"}

        start = time.perf_counter()
        result = profiler.probe(path)
        elapsed = time.perf_counter() - start

        summary = result.get("summary", {})
        return {
            "elapsed": elapsed,
            "files": summary.get("total_files", 0),
            "dirs": summary.get("total_folders", 0),
        }

    except Exception as e:
        return {"error": str(e)}


def run_benchmark_suite(
    path: str,
    iterations: int = 3,
    clear_cache: bool = False,
    no_ignore: bool = False,
    backends: Optional[List[str]] = None,
) -> Dict[str, Dict]:
    """Run complete benchmark suite on a path.

    Args:
        path: Directory to benchmark
        iterations: Number of iterations per method
        clear_cache: Clear filesystem cache between runs
        no_ignore: Ignore .gitignore files
        backends: List of backends to test (default: all)

    Returns:
        Dict mapping method names to results
    """
    if backends is None:
        backends = ["os.walk", "pathlib", "rust", "rust-seq", "async", "fd", "python"]

    results = {}

    for method in backends:
        times = []
        last_result = None

        for i in range(iterations):
            if clear_cache and i > 0:
                clear_filesystem_cache()

            if method == "os.walk":
                elapsed, files, dirs = benchmark_os_walk(path)
                last_result = {"files": files, "dirs": dirs}
            elif method == "pathlib":
                elapsed, files, dirs = benchmark_pathlib(path)
                last_result = {"files": files, "dirs": dirs}
            else:
                result = benchmark_filoma(path, method, no_ignore=no_ignore)
                if result and "error" not in result:
                    elapsed = result["elapsed"]
                    last_result = {"files": result["files"], "dirs": result["dirs"]}
                else:
                    # Backend not available
                    results[method] = {"error": result.get("error", "Unknown error") if result else "Failed"}
                    break

            times.append(elapsed)

        if times and last_result:
            avg_time = sum(times) / len(times)
            results[method] = {
                "avg_time": avg_time,
                "min_time": min(times),
                "max_time": max(times),
                "files": last_result["files"],
                "dirs": last_result["dirs"],
                "files_per_sec": last_result["files"] / avg_time if avg_time > 0 else 0,
            }

    return results


# =============================================================================
# Output Formatting
# =============================================================================


def print_results(results: Dict[str, Dict], title: str = "Benchmark Results"):
    """Print formatted benchmark results."""
    print(f"\n{'=' * 70}")
    print(f"📊 {title}")
    print("=" * 70)

    # Filter out errors for the main table
    valid_results = {k: v for k, v in results.items() if "error" not in v}
    error_results = {k: v for k, v in results.items() if "error" in v}

    if not valid_results:
        print("No valid results to display.")
        return

    # Find baseline (os.walk if available, else first result)
    baseline_time = valid_results.get("os.walk", {}).get("avg_time")
    if not baseline_time:
        baseline_time = next(iter(valid_results.values()))["avg_time"]

    # Sort by average time
    sorted_results = sorted(valid_results.items(), key=lambda x: x[1]["avg_time"])

    print(f"\n{'Method':<15} {'Avg Time':>10} {'Files/sec':>12} {'Speedup':>10} {'Files':>10}")
    print("-" * 70)

    for method, data in sorted_results:
        speedup = baseline_time / data["avg_time"] if data["avg_time"] > 0 else 0
        speedup_str = f"{speedup:.2f}x" if method != "os.walk" else "(base)"
        print(f"{method:<15} {data['avg_time']:>9.3f}s {data['files_per_sec']:>11,.0f} {speedup_str:>10} {data['files']:>10,}")

    # Show errors
    if error_results:
        print(f"\n⚠️  Unavailable backends:")
        for method, data in error_results.items():
            print(f"   {method}: {data['error']}")


# =============================================================================
# Main CLI
# =============================================================================


def main():
    """Run the benchmark CLI."""
    parser = argparse.ArgumentParser(
        description="Benchmark filoma performance across different backends and storage types.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Quick benchmark of current directory
  python benchmarks/benchmark.py .

  # Benchmark with auto-generated test data
  python benchmarks/benchmark.py --path /tmp/bench --setup-dataset

  # Large dataset benchmark
  python benchmarks/benchmark.py --path /tmp/bench --setup-dataset --dataset-size large

  # Compare multiple storage locations
  python benchmarks/benchmark.py --path local=/tmp --path nas=/mnt/nas

  # Accurate cold-cache benchmark (requires sudo)
  python benchmarks/benchmark.py --path /data --iterations 5 --clear-cache
        """,
    )

    parser.add_argument(
        "path",
        nargs="?",
        help="Path to benchmark (simple mode). Use --path for labeled paths.",
    )
    parser.add_argument(
        "--path",
        action="append",
        dest="paths",
        metavar="[LABEL=]PATH",
        help="Path to benchmark. Format: 'label=/path' or just '/path'. Can be repeated.",
    )
    parser.add_argument(
        "--backend",
        action="append",
        choices=["os.walk", "pathlib", "rust", "rust-seq", "async", "fd", "python", "all"],
        help="Backends to test. Can be repeated. Default: all",
    )
    parser.add_argument(
        "-n",
        "--iterations",
        type=int,
        default=3,
        help="Number of iterations per test (default: 3)",
    )
    parser.add_argument(
        "--setup-dataset",
        action="store_true",
        help="Create test dataset in target directories",
    )
    parser.add_argument(
        "--dataset-size",
        choices=list(DATASET_SIZES.keys()),
        default="medium",
        help="Size of generated dataset (default: medium)",
    )
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Clear filesystem cache between runs (requires sudo)",
    )
    parser.add_argument(
        "--no-ignore",
        action="store_true",
        help="Ignore .gitignore files for fair comparison",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Delete test directories after benchmarking",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Save results to file",
    )

    args = parser.parse_args()

    # Collect paths
    paths = []
    if args.path:
        paths.append(("default", args.path))
    if args.paths:
        for p in args.paths:
            if "=" in p:
                label, path_str = p.split("=", 1)
            else:
                label = Path(p).name or "root"
                path_str = p
            paths.append((label, path_str))

    if not paths:
        parser.print_help()
        print("\n❌ Error: No path specified. Provide a path as argument or use --path.")
        sys.exit(1)

    # Determine backends
    backends = args.backend or ["all"]
    if "all" in backends:
        backends = ["os.walk", "pathlib", "rust", "rust-seq", "async", "fd", "python"]
    backends = list(dict.fromkeys(backends))  # Deduplicate

    # Dataset size
    num_dirs, files_per_dir = DATASET_SIZES[args.dataset_size]

    # Setup datasets if requested
    for label, path_str in paths:
        path_obj = Path(path_str)
        if args.setup_dataset:
            print(f"📁 Setting up test dataset: {label} ({path_str})")
            print(f"   Size: {args.dataset_size} ({num_dirs} dirs × {files_per_dir} files)")
            total_files, total_dirs = create_test_structure(
                path_obj,
                num_dirs=num_dirs,
                num_files_per_dir=files_per_dir,
            )
            print(f"   ✅ Created {total_files:,} files in {total_dirs:,} directories")
        elif not path_obj.exists():
            print(f"❌ Path does not exist: {path_str}")
            print("   💡 Use --setup-dataset to create a test dataset")
            sys.exit(1)

    # Print configuration
    print(f"\n🚀 Filoma Benchmark")
    print("=" * 70)
    print(f"Iterations:    {args.iterations}")
    print(f"Cache clear:   {'Yes (requires sudo)' if args.clear_cache else 'No'}")
    print(f"Backends:      {', '.join(backends)}")
    print(f"Targets:       {', '.join(f'{l} ({p})' for l, p in paths)}")

    # Run benchmarks
    all_results = {}
    for label, path_str in paths:
        print(f"\n📂 Benchmarking: {label} ({path_str})")
        results = run_benchmark_suite(
            path_str,
            iterations=args.iterations,
            clear_cache=args.clear_cache,
            no_ignore=args.no_ignore,
            backends=backends,
        )
        all_results[label] = results
        print_results(results, f"Results: {label}")

    # Comparative analysis for multiple paths
    if len(paths) > 1:
        print(f"\n{'=' * 70}")
        print("📊 Comparative Analysis")
        print("=" * 70)

        first_label = paths[0][0]
        first_results = all_results.get(first_label, {})

        for label, _path in paths[1:]:
            print(f"\n{label} vs {first_label}:")
            other_results = all_results.get(label, {})

            for backend in backends:
                if backend in first_results and backend in other_results:
                    if "error" in first_results[backend] or "error" in other_results[backend]:
                        continue
                    first_time = first_results[backend]["avg_time"]
                    other_time = other_results[backend]["avg_time"]
                    if first_time > 0:
                        ratio = other_time / first_time
                        status = "slower" if ratio > 1 else "faster"
                        print(f"  {backend:<12}: {ratio:.2f}x {status} ({other_time:.3f}s vs {first_time:.3f}s)")

    # Save results
    if args.output:
        import json

        with open(args.output, "w") as f:
            json.dump(all_results, f, indent=2, default=str)
        print(f"\n💾 Results saved to {args.output}")

    # Cleanup
    if args.cleanup:
        print("\n🧹 Cleaning up...")
        for label, path_str in paths:
            try:
                path_obj = Path(path_str)
                if path_obj.exists():
                    print(f"   Removing {path_str}...")
                    shutil.rmtree(path_obj)
            except Exception as e:
                print(f"   ❌ Error: {e}")


if __name__ == "__main__":
    main()
