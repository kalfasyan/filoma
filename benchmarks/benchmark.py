#!/usr/bin/env python3
"""Unified benchmark script for filoma performance testing.

Compares filoma backends (Rust, fd, Python, async) against standard library alternatives.
Supports both local and network storage benchmarking with configurable test datasets.

Examples
--------
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
import logging
import os
import platform
import shutil
import subprocess
import sys
import time
from multiprocessing import cpu_count
from pathlib import Path
from statistics import median
from typing import Dict, List, Optional, Tuple

try:
    from filoma.directories import DirectoryProfiler, DirectoryProfilerConfig
except ImportError:
    print("❌ filoma not installed. Install with: pip install filoma")
    sys.exit(1)

# Suppress filoma logging during benchmarks
logging.getLogger("filoma").setLevel(logging.WARNING)

# Try to import the async Rust function directly for benchmarking
try:
    from filoma.filoma_core import probe_directory_rust_async

    ASYNC_AVAILABLE = True
except ImportError:
    ASYNC_AVAILABLE = False


# =============================================================================
# Backend Groups
# =============================================================================

# Traversal-only backends (just visit files, no metadata)
# Includes fast variants of rust backends that skip metadata collection
TRAVERSAL_BACKENDS = ["os.walk", "pathlib", "rust-fast", "async-fast"]

# Full profiling backends (collect metadata, extensions, stats)
PROFILING_BACKENDS = ["rust", "rust-seq", "async", "fd", "python"]

# All backends
ALL_BACKENDS = TRAVERSAL_BACKENDS + PROFILING_BACKENDS


# =============================================================================
# Test Data Generation
# =============================================================================

DATASET_SIZES = {
    "small": (10, 100),  # ~1,000 files
    "medium": (50, 200),  # ~10,000 files
    "large": (100, 500),  # ~50,000 files
    "xlarge": (200, 1000),  # ~200,000 files
    "xxlarge": (10000, 100),  # ~1,000,000 files
}


def create_test_structure(
    path: Path,
    num_dirs: int = 50,
    num_files_per_dir: int = 50,
    depth: int = 1,
) -> Tuple[int, int]:
    """Create a test directory structure for benchmarking.

    Args:
    ----
        path: Base directory to create structure in
        num_dirs: Number of directories at each level
        num_files_per_dir: Number of files per directory
        depth: Number of nested subdirectory levels (default 1 for flat structure)

    Returns:
    -------
        Tuple of (total_files, total_dirs) created

    """
    extensions = ["txt", "py", "rs", "md", "json", "yaml", "csv", "log"]
    total_files = 0
    total_dirs = 0

    path.mkdir(parents=True, exist_ok=True)
    print(
        f"   Creating {num_dirs} directories with {num_files_per_dir} files each...",
        flush=True,
    )

    for i in range(num_dirs):
        if i > 0 and i % 50 == 0:
            print(
                f"   ... created {i}/{num_dirs} directories ({total_files:,} files)",
                flush=True,
            )

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

        # Create nested subdirectories (only if depth > 1)
        if depth > 1:
            for k in range(min(3, num_dirs // 20 or 1)):
                sub_files, sub_dirs = create_test_structure(
                    dir_path / f"sub_{k:02d}",
                    num_dirs=max(2, num_dirs // 20),
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

    Returns
    -------
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
    ----
        path: Directory path to scan
        backend: Backend to use ('rust', 'rust-seq', 'async', 'fd', 'python')
        no_ignore: Ignore .gitignore files for fair comparison

    Returns:
    -------
        Dict with timing and counts, or None if backend unavailable

    """
    # Handle async variants (async and async-fast)
    if backend in ("async", "async-fast"):
        if not ASYNC_AVAILABLE:
            return {"error": "Async Rust not available"}
        fast_path = backend == "async-fast"
        try:
            start = time.perf_counter()
            result = probe_directory_rust_async(
                path,
                None,  # max_depth
                64,  # concurrency_limit
                5000,  # timeout_ms
                0,  # retries
                fast_path,  # fast_path_only
                True,  # follow_links
                True,  # search_hidden
                True,  # no_ignore - always ignore .gitignore for consistent counts
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

    # Handle rust-fast variant
    fast_path_only = backend == "rust-fast"
    actual_backend = "rust" if backend == "rust-fast" else backend

    # Configure based on backend
    use_rust = actual_backend in ("rust", "rust-seq")
    use_parallel = actual_backend == "rust"
    search_backend = "fd" if actual_backend == "fd" else ("rust" if use_rust else "python")

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
            fast_path_only=fast_path_only,
        )
        profiler = DirectoryProfiler(config)

        # Check availability
        if actual_backend in ("rust", "rust-seq") and not profiler.is_rust_available():
            return {"error": "Rust not available"}
        if actual_backend == "fd" and not profiler.is_fd_available():
            return {"error": "fd not available"}

        start = time.perf_counter()

        # Suppress loguru logging during benchmark run
        try:
            from loguru import logger

            logger.disable("filoma")
        except ImportError:
            pass

        result = profiler.probe(path)

        try:
            from loguru import logger

            logger.enable("filoma")
        except ImportError:
            pass

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
    ----
        path: Directory to benchmark
        iterations: Number of iterations per method
        clear_cache: Clear filesystem cache between runs
        no_ignore: Ignore .gitignore files
        backends: List of backends to test (default: profiling backends)

    Returns:
    -------
        Dict mapping method names to results

    """
    if backends is None:
        backends = PROFILING_BACKENDS.copy()

    # Disable Rust logging
    env = os.environ.copy()
    env["RUST_LOG"] = ""

    results = {}
    total_methods = len(backends)

    for method_idx, method in enumerate(backends, 1):
        # Clear cache before each backend for fair comparison
        if clear_cache:
            if not clear_filesystem_cache():
                print("    ⚠️  Cache not cleared - results may not reflect cold-cache performance")

        print(f"  [{method_idx}/{total_methods}] Testing {method}...", end=" ", flush=True)
        times = []
        last_result = None

        for i in range(iterations):
            # Also clear cache between iterations (skip first since we just cleared)
            if clear_cache and i > 0:
                if not clear_filesystem_cache():
                    pass  # Warning already shown once

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
                    print(f"✗ {result.get('error', 'Unknown error') if result else 'Failed'}")
                    results[method] = {"error": (result.get("error", "Unknown error") if result else "Failed")}
                    break

            times.append(elapsed)
            print(f"iter{i + 1}={elapsed:.2f}s", end=" ", flush=True)

        if times and last_result:
            median_time = median(times)
            avg_time = sum(times) / len(times)
            print(f"✓ median={median_time:.2f}s")
            results[method] = {
                "median_time": median_time,
                "avg_time": avg_time,
                "min_time": min(times),
                "max_time": max(times),
                "files": last_result["files"],
                "dirs": last_result["dirs"],
                "files_per_sec": (last_result["files"] / median_time if median_time > 0 else 0),
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

    # Find baseline: prefer rust (fastest profiling backend), then os.walk, then first result
    baseline_method = None
    baseline_time = None
    for candidate in ["rust", "os.walk"]:
        if candidate in valid_results:
            baseline_method = candidate
            baseline_time = valid_results[candidate]["median_time"]
            break
    if not baseline_time:
        baseline_method = next(iter(valid_results.keys()))
        baseline_time = valid_results[baseline_method]["median_time"]

    # Sort by median time (fastest first)
    sorted_results = sorted(valid_results.items(), key=lambda x: x[1]["median_time"])

    print(f"\n{'Method':<15} {'Median Time':>12} {'Files/sec':>12} {'Speedup':>10} {'Files':>10}")
    print("-" * 70)

    for method, data in sorted_results:
        speedup = baseline_time / data["median_time"] if data["median_time"] > 0 else 0
        speedup_str = f"{speedup:.2f}x" if method != baseline_method else "(base)"
        print(f"{method:<15} {data['median_time']:>11.3f}s {data['files_per_sec']:>11,.0f} {speedup_str:>10} {data['files']:>10,}")

    print("\n(Results sorted by median time - execution order shown during benchmark)")

    # Show errors
    if error_results:
        print("\n⚠️  Unavailable backends:")
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
        choices=[
            "os.walk",
            "pathlib",
            "rust",
            "rust-seq",
            "rust-fast",
            "async",
            "async-fast",
            "fd",
            "python",
            "all",
            "profiling",
            "traversal",
        ],
        help="Backends to test. Groups: 'profiling' (full metadata), 'traversal' (fast path only). Default: profiling",
    )
    parser.add_argument(
        "-n",
        "--iterations",
        type=int,
        default=3,
        help="Number of iterations per test (default: 3)",
    )
    parser.add_argument(
        "--use-existing",
        action="store_true",
        help="Use existing directory as-is (don't create test data)",
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
        "--no-cleanup",
        action="store_true",
        help="Don't delete generated test directories after benchmarking",
    )
    parser.add_argument(
        "--shuffle",
        action="store_true",
        help="Randomize backend order to average out cache effects",
    )
    parser.add_argument(
        "--warmup",
        action="store_true",
        help="Run a warmup pass before benchmarking (recommended for NFS)",
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

    # Default to temp directory if no path specified
    if not paths:
        import tempfile

        temp_dir = Path(tempfile.gettempdir()) / "filoma-bench"
        paths.append(("benchmark", str(temp_dir)))

    # Determine backends (default to profiling group for fair comparison)
    backends = args.backend or ["profiling"]

    # Expand backend groups
    expanded = []
    for b in backends:
        if b == "all":
            expanded.extend(ALL_BACKENDS)
        elif b == "profiling":
            expanded.extend(PROFILING_BACKENDS)
        elif b == "traversal":
            expanded.extend(TRAVERSAL_BACKENDS)
        else:
            expanded.append(b)
    backends = list(dict.fromkeys(expanded))  # Deduplicate while preserving order

    # Shuffle backends to average out cache effects
    if args.shuffle:
        import random

        random.shuffle(backends)

    # Dataset size
    num_dirs, files_per_dir = DATASET_SIZES[args.dataset_size]

    # Track which paths we created (for cleanup)
    created_paths = []

    # Setup datasets: create if path doesn't exist (unless --use-existing)
    for label, path_str in paths:
        path_obj = Path(path_str)
        if args.use_existing:
            # User wants to use existing directory
            if not path_obj.exists():
                print(f"❌ Path does not exist: {path_str}")
                print("   💡 Remove --use-existing to auto-create test data")
                sys.exit(1)
        else:
            # Auto-create test data if path doesn't exist or is empty
            if not path_obj.exists() or not any(path_obj.iterdir()):
                print(f"📁 Creating test dataset: {label} ({path_str})")
                print(f"   Size: {args.dataset_size} ({num_dirs} dirs × {files_per_dir} files)")
                total_files, total_dirs = create_test_structure(
                    path_obj,
                    num_dirs=num_dirs,
                    num_files_per_dir=files_per_dir,
                )
                print(f"   ✅ Created {total_files:,} files in {total_dirs:,} directories")
                created_paths.append(path_str)

    # Print configuration
    print("\n🚀 Filoma Benchmark")
    print("=" * 70)
    print(f"Iterations:    {args.iterations}")
    print(f"Cache clear:   {'Yes (requires sudo)' if args.clear_cache else 'No'}")
    print(f"Shuffle:       {'Yes' if args.shuffle else 'No'}")
    print(f"Warmup:        {'Yes' if args.warmup else 'No'}")
    print(f"Backends:      {', '.join(backends)}")
    print(f"Targets:       {', '.join(f'{q} ({p})' for q, p in paths)}")

    # Run warmup pass to prime NFS server cache
    if args.warmup:
        print("\n🔥 Warmup pass (priming NFS cache)...")
        for label, path_str in paths:
            print(f"   Warming up {label}...", end=" ", flush=True)
            # Use os.walk for warmup - fast and touches all entries
            for _root, _dirs, _files in os.walk(path_str):
                pass
            print("done")
        if args.clear_cache:
            print("   Clearing local cache after warmup...")
            clear_filesystem_cache()

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

    # Cleanup created directories (unless --no-cleanup)
    if created_paths and not args.no_cleanup:
        print("\n🧹 Cleaning up generated test data...")
        for path_str in created_paths:
            try:
                path_obj = Path(path_str)
                if path_obj.exists():
                    print(f"   Removing {path_str}...")
                    shutil.rmtree(path_obj)
            except Exception as e:
                print(f"   ❌ Error: {e}")


if __name__ == "__main__":
    main()
