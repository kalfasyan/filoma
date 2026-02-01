# Performance Benchmarks

**Latest Benchmark Data**: Updated February 2026 with accurate measurements on network storage.

> ⚠️ **DISCLAIMER**: Benchmark results vary based on hardware, filesystem, and directory structure. Always run your own benchmarks on your target systems for accurate performance data specific to your use case.

## Benchmark Methodology

### Cache Management & Fair Testing
All benchmarks use controlled cache clearing to represent real-world performance:

- `--clear-cache`: Clears filesystem cache before each backend (prevents warm-cache bias)
- `--warmup`: Single warmup iteration before timed runs (eliminates cold-start artifacts)
- `--shuffle`: Randomizes backend execution order (prevents first-run advantage)
- **Iterations**: 3 runs per backend, results reported as median

### Test Dataset
- **Format**: Synthetic XLarge dataset (200,000 files) for reproducibility
- **Location**: Network storage (/XYZdata NFS mount) for realistic I/O patterns
- **Controlled**: Consistent structure across all benchmark runs

## Performance Results

### Latest Results (XLarge Dataset, Network Storage, Profiling)
*200,000 files - Full metadata collection - Median of 3 trials*

**Test Command:**
```bash
uv run python benchmarks/benchmark.py \
    --path /XYZdata/tmp_yk/bench-test \
    --dataset-size xlarge \
    --backend profiling \
    -n 3 --clear-cache --warmup --shuffle
```

```
Backend      │ Median Time │ Files/sec  │ Relative Speed
─────────────┼─────────────┼────────────┼───────────────
Rust         │ 2.331s      │ 85,807     │ 1.00x (baseline)
Async        │ 2.842s      │ 70,384     │ 0.82x
Rust-seq     │ 8.584s      │ 23,300     │ 0.27x
fd           │ 14.386s     │ 13,902     │ 0.16x
Python       │ 15.146s     │ 13,205     │ 0.15x
```

**Key Observations:**
- Rust parallel remains fastest for network storage
- Async backend (tokio) shows good performance on NFS with high-latency operations
- Sequential backends show their limitations at scale
- Results from actual network filesystem (/vitodata) reflect real-world performance

### Traversal Performance (XLarge Dataset, Fast-Path Only)
*200,000 files - File path discovery without metadata collection - Median of 3 trials*

**Test Command:**
```bash
uv run python benchmarks/benchmark.py \
    --path /XYZdata/tmp_yk/bench-test \
    --dataset-size xlarge \
    --backend traversal \
    -n 3 --clear-cache --warmup --shuffle
```

```
Backend      │ Median Time │ Files/sec  │ Relative Speed
─────────────┼─────────────┼────────────┼───────────────
os.walk      │ 0.412s      │ 485,171    │ 1.00x (baseline)
rust-fast    │ 0.640s      │ 312,698    │ 0.64x
async-fast   │ 2.742s      │ 72,931     │ 0.15x
pathlib      │ 9.933s      │ 20,136     │ 0.04x
```

**Key Observations:**
- Rust fast-path is slower than pure os.walk for simple path discovery (0.64x)
- Python `os.walk` is very efficient for discovery-only workloads
- Async-fast introduces significant overhead when metadata collection is skipped
- Pathlib's recursive glob remains slowest at scale
- Fast-path variants show less advantage than profiling backends due to lower computational overhead

### Key Insights

- **🦀 Rust excels at metadata collection** - Fastest for profiling benchmarks (2.331s baseline), but slower than os.walk for discovery-only
- **⚡ Async is strong alternative** - 0.82x of Rust on profiling with good network I/O handling, but introduces overhead for discovery
- **🐍 Python dominates pure discovery** - os.walk is fastest for traversal-only (0.412s), showing Python's efficiency when I/O is minimal
- **🎯 Backend selection depends on task** - Use Rust for metadata collection, Python for discovery-only on network storage
- **❄️ Cache clearing is critical** - Without `--clear-cache`, warm-cache bias makes results unrealistic
- **⏱️ Warmup and shuffle matter** - `--warmup` eliminates cold-start artifacts; `--shuffle` prevents positional advantage

## Backend Groups for Fair Comparisons

The benchmark tool separates backends into groups to ensure fair performance comparisons:

### Profiling Backends
These backends perform full metadata collection (permissions, sizes, timestamps, etc.):
- **Rust** - Rayon parallel scanner, most optimized for metadata collection
- **Rust-seq** - Sequential Rust baseline for comparison
- **Async** - Tokio async scanner, excellent for high-latency network operations
- **fd** - External tool, traversal optimized but good reference point
- **Python** - Pure Python with os.walk, always available baseline

Use profiling backends to benchmark complete directory scanning with all metadata:
```bash
python benchmarks/benchmark.py /path -n 3 --backend profiling
```

### Traversal Backends  
These backends only discover file paths (fast-path mode - no metadata collection):
- **os.walk** - Python standard library baseline
- **pathlib** - Python pathlib.Path.rglob
- **rust-fast** - Rust with `fast_path_only=True` for pure discovery
- **async-fast** - Async with `fast_path_only=True` for pure discovery

Use traversal backends to measure raw discovery performance:
```bash
python benchmarks/benchmark.py /path -n 3 --backend traversal
```

This separation is important because:
1. **Fair comparisons** - Profiling and traversal measure different capabilities
2. **Realistic expectations** - Fast-path shows what's possible with just path discovery
3. **Use case matching** - Choose comparison group matching your actual use case
4. **Methodology clarity** - Eliminates confusion about what's being measured

## Network Storage Notes

Results above are from actual network-mounted storage (/XYZdata) with NFS protocol:
- **Rust parallel** excels even on network storage, thanks to bounded concurrency and work-queue pattern
- **Async backend** is competitive alternative with lower CPU overhead for high-latency operations
- **fd** is available but was not benchmarked in latest tests

Network I/O patterns are different from local storage—your results may vary based on NFS server, latency, and network configuration.

## Benchmarking Best Practices

### Accurate Performance Testing

```python
import subprocess
import time
from filoma.directories import DirectoryProfiler

def clear_filesystem_cache():
    """Clear OS filesystem cache for realistic benchmarks."""
    subprocess.run(['sync'], check=True)
    subprocess.run(['sudo', 'tee', '/proc/sys/vm/drop_caches'], 
                   input='3\n', text=True, stdout=subprocess.DEVNULL, check=True)
    time.sleep(1)  # Let cache clear settle

def benchmark_backend(backend_name, path, iterations=3):
    """Benchmark a specific backend with cold cache."""
    profiler = DirectoryProfiler(DirectoryProfilerConfig(search_backend=backend_name, show_progress=False))
    
    # Check if the specific backend is available
    available = ((backend_name == "rust" and profiler.is_rust_available()) or
                (backend_name == "fd" and profiler.is_fd_available()) or
                (backend_name == "python"))  # Python always available
    if not available:
        return None
        
    times = []
    for i in range(iterations):
        clear_filesystem_cache()
        start = time.time()
    result = profiler.probe(path)
        elapsed = time.time() - start
        times.append(elapsed)
        
    avg_time = sum(times) / len(times)
    files_per_sec = result['summary']['total_files'] / avg_time
    
    return {
        'backend': backend_name,
        'avg_time': avg_time,
        'files_per_sec': files_per_sec,
        'total_files': result['summary']['total_files']
    }

# Example usage
results = []
for backend in ['rust', 'fd', 'python']:
    result = benchmark_backend(backend, '/test/directory')
    if result:
        results.append(result)
        print(f"{backend}: {result['avg_time']:.3f}s ({result['files_per_sec']:.0f} files/sec)")

# Find fastest
if results:
    fastest = min(results, key=lambda x: x['avg_time'])
    print(f"\n🏆 Fastest: {fastest['backend']}")
```

### Performance Tips

1. **Disable progress bars** for benchmarking: `show_progress=False`
2. **Use fast path only** for discovery benchmarks: `fast_path_only=True`
3. **Clear filesystem cache** between runs for realistic results
4. **Run multiple iterations** and average the results
5. **Test on your target storage** - results vary by filesystem type

### Warm vs Cold Cache Comparison

```python
# Cold cache (realistic)
clear_filesystem_cache()
start = time.time()
result = profiler.probe("/test/directory")
cold_time = time.time() - start

# Warm cache (for comparison only)
start = time.time()
result = profiler.probe("/test/directory")  
warm_time = time.time() - start

print(f"Cold cache: {cold_time:.3f}s (realistic)")
print(f"Warm cache: {warm_time:.3f}s (cached, {cold_time/warm_time:.1f}x slower when cold)")
```

> **⚠️ Important**: Always use cold cache for realistic benchmarks. Warm cache results can be 
> 2-8x faster but don't represent real-world performance for first-time directory access.

## Backend Selection Recommendations

| Use Case | Recommended Backend | Why |
|----------|-------------------|-----|
| **Large directories** | Auto (Rust if available) | Best overall performance |
| **Network filesystems** | `fd` | Optimized for network I/O |
| **CI/CD environments** | Auto | Reliable with graceful fallbacks |
| **Maximum compatibility** | `python` | Always works, no dependencies |
| **DataFrame analysis** | Auto (Rust if available) | Fastest DataFrame building |
| **Pattern matching** | `fd` | Advanced regex/glob support |

## Your Results May Vary

Performance depends on:
- **Storage type** - NVMe SSD > SATA SSD > HDD
- **Filesystem** - ext4, NTFS, APFS, NFS all behave differently  
- **Directory structure** - Deep vs wide, file size distribution
- **System load** - CPU, memory, I/O contention
- **Network latency** - Critical for NFS/network storage

Run your own benchmarks on your target systems for accurate performance data.