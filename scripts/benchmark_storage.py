#!/usr/bin/env python3
"""Benchmark script for comparing filoma performance across different storage types.

Focuses on "local" vs "network" storage and fair cache handling.
"""

import argparse
import platform
import shutil
import subprocess
import sys
import time
from multiprocessing import cpu_count
from pathlib import Path
from typing import Dict

# Add the src directory to path so we can import filoma if it's not installed
project_root = Path(__file__).resolve().parent.parent
if (project_root / "src").exists():
    sys.path.insert(0, str(project_root / "src"))

try:
    from filoma.directories import DirectoryProfiler, DirectoryProfilerConfig
except ImportError as e:
    print(f"❌ Could not import filoma: {e}")
    print("Please ensure it is installed or run from the project root.")
    sys.exit(1)


def create_test_structure(path: Path, num_dirs: int = 100, num_files_per_dir: int = 50):
    """Create a test directory structure for benchmarking."""
    print(f"   Creating test structure in {path}")
    print(f"   ({num_dirs} directories x {num_files_per_dir} files = {num_dirs * num_files_per_dir} total files)...")

    path.mkdir(parents=True, exist_ok=True)

    for i in range(num_dirs):
        dir_path = path / f"test_dir_{i:03d}"
        dir_path.mkdir(parents=True, exist_ok=True)

        for j in range(num_files_per_dir):
            file_path = dir_path / f"file_{j:03d}.{['txt', 'py', 'rs', 'md', 'json'][j % 5]}"
            # Only write if file doesn't exist to save time on re-runs
            if not file_path.exists():
                file_path.write_text(f"Test content for file {j} in directory {i}")

    print(f"   ✅ Created dataset in {path}")


def clear_system_cache(dry_run: bool = False) -> bool:
    """Clear the OS filesystem cache.

    Requires sudo privileges.
    """
    system = platform.system()

    if dry_run:
        print(f"   [Dry Run] Would clear cache for {system}")
        return True

    try:
        if system == "Linux":
            # Flush file system buffers
            subprocess.run(["sync"], check=True)
            # Clear pagecache, dentries, and inodes
            subprocess.run(["sudo", "sh", "-c", "echo 3 > /proc/sys/vm/drop_caches"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        elif system == "Darwin":  # macOS
            subprocess.run(["sync"], check=True)
            subprocess.run(["sudo", "purge"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        else:
            print(f"⚠️  Cache clearing not implemented for {system}")
            return False

        return True
    except subprocess.CalledProcessError:
        print("⚠️  Failed to clear cache. Sudo password might be required or permissions denied.")
        return False
    except Exception as e:
        print(f"⚠️  Error clearing cache: {e}")
        return False


def run_benchmark(path: str, backend: str, iterations: int, do_clear_cache: bool, fast_path: bool = False, no_ignore: bool = False) -> Dict:
    """Run benchmark for a specific configuration."""
    # Configure profiler
    use_rust = backend in ["rust", "rust-seq"]
    use_parallel = backend == "rust"
    search_backend = "fd" if backend == "fd" else ("rust" if use_rust else "python")

    # Optimize fd backend by using all available CPU threads
    fd_threads = None
    if backend == "fd":
        fd_threads = cpu_count()

    config = DirectoryProfilerConfig(
        use_rust=use_rust, use_parallel=use_parallel, search_backend=search_backend, show_progress=False, fd_no_ignore=no_ignore, threads=fd_threads
    )

    profiler = DirectoryProfiler(config)

    # Check availability
    if backend == "rust" and not profiler.is_parallel_available():
        return {"error": "Rust parallel not available"}
    if backend == "rust-seq" and not profiler.is_rust_available():
        return {"error": "Rust not available"}
    if backend == "fd" and not profiler.is_fd_available():
        return {"error": "fd not available"}

    times = []
    total_files = 0

    for i in range(iterations):
        if do_clear_cache:
            success = clear_system_cache()
            if success:
                # Small sleep to let disk settle
                time.sleep(1)

        start_time = time.time()

        if fast_path:
            # If we just want to test discovery speed without full metadata overhead
            # We can use the lower level methods or just probe and ignore result
            # But probe() does full metadata collection by default.
            # filoma doesn't currently expose a pure "discovery only" public API easily
            # without collecting stats, but probe() is what users use.
            pass

        result = profiler.probe(path)

        duration = time.time() - start_time
        times.append(duration)

        # Capture file count from the last run
        if "summary" in result:
            total_files = result["summary"]["total_files"]
        else:
            total_files = 0  # Should not happen

    avg_time = sum(times) / len(times)
    min_time = min(times)
    max_time = max(times)

    return {
        "avg_time": avg_time,
        "min_time": min_time,
        "max_time": max_time,
        "files_per_sec": total_files / avg_time if avg_time > 0 else 0,
        "total_files": total_files,
    }


def main():
    """Run the benchmark comparing filoma performance across backends."""
    parser = argparse.ArgumentParser(description="Benchmark filoma on local vs network storage.")
    parser.add_argument(
        "--path",
        action="append",
        help="Path to benchmark in format 'label=path' (e.g. 'local=/tmp', 'nas=/mnt/nas'). Can be used multiple times.",
        required=True,
    )
    parser.add_argument(
        "--backend",
        action="append",
        choices=["python", "rust", "rust-seq", "fd", "all"],
        help="Backends to test. Default: all",
    )
    parser.add_argument("--iterations", "-n", type=int, default=3, help="Number of iterations per test. Default: 3")
    parser.add_argument("--clear-cache", action="store_true", help="Attempt to clear OS filesystem cache between runs (requires sudo).")
    parser.add_argument("--setup-dataset", action="store_true", help="Create a standard test dataset in the target directories before benchmarking.")
    parser.add_argument("--cleanup", action="store_true", help="Delete the target directories after benchmarking is complete.")
    parser.add_argument("--no-ignore", action="store_true", help="Force fd and other backends to ignore .gitignore files for fair raw comparison.")
    parser.add_argument("--output", "-o", type=str, help="Save the benchmark results to a file.")
    parser.add_argument(
        "--dataset-size", type=str, choices=["small", "medium", "large"], default="medium", help="Size of dataset to generate (default: medium)"
    )

    args = parser.parse_args()

    # Define dataset sizes
    dataset_sizes = {
        "small": (10, 20),  # 200 files
        "medium": (50, 50),  # 2,500 files
        "large": (500, 200),  # 100,000 files
    }
    num_dirs, files_per_dir = dataset_sizes[args.dataset_size]

    # Parse paths
    targets = []
    for p in args.path:
        if "=" in p:
            label, path_str = p.split("=", 1)
        else:
            label = Path(p).name
            path_str = p

        path_obj = Path(path_str)

        # Handle dataset setup or validation
        if args.setup_dataset:
            if not path_obj.exists():
                print(f"Creating directory: {path_str}")
                path_obj.mkdir(parents=True, exist_ok=True)
            create_test_structure(path_obj, num_dirs, files_per_dir)

        if not path_obj.exists():
            print(f"⚠️  Path does not exist: {path_str} ({label})")
            if not args.setup_dataset:
                print("   💡 Hint: Add --setup-dataset to automatically create and populate this directory.")
            continue
        targets.append((label, path_str))

    if not targets:
        print("❌ No valid paths provided.")
        sys.exit(1)

    # Determine backends
    backends = args.backend if args.backend else ["all"]
    if "all" in backends:
        backends = ["python", "rust", "rust-seq", "fd"]

    # Deduplicate backends while preserving order
    backends = list(dict.fromkeys(backends))

    print("\n🚀 Filoma Storage Benchmark")
    print("==========================")
    print(f"Cache Clearing: {'ENABLED (Requires sudo)' if args.clear_cache else 'DISABLED'}")
    print(f"Iterations:     {args.iterations}")
    print(f"Backends:       {', '.join(backends)}")
    print(f"Targets:        {', '.join([f'{t[0]} ({t[1]})' for t in targets])}")
    print()

    results = {}
    report_lines = []

    for label, path in targets:
        target_header = []
        target_header.append(f"\n📂 Benchmarking Target: {label}")
        target_header.append(f"   Path: {path}")
        target_header.append("-" * 60)
        target_header.append(f"{'Backend':<15} | {'Avg Time':<10} | {'Files/sec':<12} | {'Total Files':<12}")
        target_header.append("-" * 60)

        for line in target_header:
            print(line)
        report_lines.extend(target_header)

        target_results = {}

        for backend in backends:
            res = run_benchmark(path, backend, args.iterations, args.clear_cache, no_ignore=args.no_ignore)

            if "error" in res:
                line = f"{backend:<15} | {'N/A (' + res['error'] + ')':<30}"
                print(line)
                report_lines.append(line)
                continue

            line = f"{backend:<15} | {res['avg_time']:<9.3f}s | {res['files_per_sec']:<11.0f} | {res['total_files']:<12}"
            print(line)
            report_lines.append(line)
            target_results[backend] = res

        results[label] = target_results

    # Summary Analysis
    if len(targets) > 1 and "local" in [t[0].lower() for t in targets]:
        summary_header = []
        summary_header.append("\n\n📊 Comparative Analysis")
        summary_header.append("=======================")

        for line in summary_header:
            print(line)
        report_lines.extend(summary_header)

        # Find local target
        local_label = next(t[0] for t in targets if t[0].lower() == "local")
        local_res = results.get(local_label)

        if local_res:
            for label, path in targets:
                if label == local_label:
                    continue

                line = f"\nComparing {label} vs {local_label}:"
                print(line)
                report_lines.append(line)

                other_res = results.get(label)
                if not other_res:
                    continue

                for backend in backends:
                    if backend in local_res and backend in other_res:
                        l_time = local_res[backend]["avg_time"]
                        o_time = other_res[backend]["avg_time"]

                        if l_time > 0:
                            ratio = o_time / l_time
                            line = f"  {backend:<10}: {ratio:.2f}x slower than local ({o_time:.3f}s vs {l_time:.3f}s)"
                            print(line)
                            report_lines.append(line)

    # Save to file
    if args.output:
        print(f"\n💾 Saving report to {args.output}...")
        try:
            with open(args.output, "w") as f:
                f.write("\n".join(report_lines))
        except Exception as e:
            print(f"❌ Error saving report: {e}")

    # Cleanup
    if args.cleanup:
        print("\n🧹 Cleaning up...")
        for label, path in targets:
            try:
                path_obj = Path(path)
                if path_obj.exists():
                    print(f"   Removing {path} ({label})...")
                    shutil.rmtree(path_obj)
            except Exception as e:
                print(f"❌ Error cleaning up {path}: {e}")


if __name__ == "__main__":
    main()
