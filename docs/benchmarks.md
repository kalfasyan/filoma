# Performance Benchmarks

## Test Environment

*All performance data measured on the following system:*

```
OS:         Linux x86_64 (Ubuntu-based)
Storage:    WD_BLACK SN770 2TB NVMe SSD (Sandisk Corp)
Filesystem: ext4 (non-NFS, local storage)
Memory:     High-speed access to NVMe storage
CPU:        Multi-core with parallel processing support
```

> **📊 Why This Matters**: SSD vs HDD performance can vary dramatically. NVMe SSDs provide 
> exceptional random I/O performance that benefits all backends. Network filesystems (NFS) 
> may show different characteristics. Your mileage may vary based on storage type.

## Benchmark Methodology

### ❄️ Cold Cache Testing
**Critical**: All benchmarks use **cold cache** methodology to represent real-world performance:

```bash
# Before each test:
sync                                    # Flush buffers
echo 3 > /proc/sys/vm/drop_caches      # Clear filesystem cache
```

> **🔥 Cache Impact**: OS filesystem cache can make benchmarks **2-8x faster** but unrealistic. 
> Warm cache results don't represent first-time directory access. Our cold cache benchmarks 
> show realistic performance for real-world usage.

### Test Dataset
- **Directory**: `/usr` (system directory with diverse file types)
- **Files**: ~250,000 files
- **Depth**: Multiple levels of nested directories
- **Size Range**: Small config files to large binaries

## Performance Results

### File Discovery Performance (Fast Path)
*Cold cache benchmarks - File path discovery only*

```
Backend      │ Time      │ Files/sec  │ Relative Speed
─────────────┼───────────┼────────────┼───────────────
Rust         │ 3.16s     │ 70,367     │ 2.28x faster
fd           │ 4.80s     │ 46,244     │ 1.50x faster  
Python       │ 8.11s     │ 30,795     │ 1.00x (baseline)
```

### DataFrame Building Performance
*Cold cache benchmarks - Full metadata collection with DataFrame creation*

```
Backend      │ Time      │ Files/sec  │ Relative Speed
─────────────┼───────────┼────────────┼───────────────
Rust         │ 4.16s     │ 53,417     │ 1.95x faster
fd           │ 4.80s     │ 46,219     │ 1.50x faster
Python       │ 8.13s     │ 30,733     │ 1.00x (baseline)
```

### Key Insights

- **🦀 Rust fastest overall** - Best performance for both file discovery and DataFrame building
- **🔍 fd competitive** - Close second, excellent alternative when Rust isn't available  
- **🐍 Python most compatible** - Works by default, reliable fallback option
- **📊 Identical results** - All backends produce the same analysis output and metadata
- **❄️ Cold vs warm cache** - Real performance is 2-8x slower than cached results
- **🎯 Automatic selection** - filoma chooses the optimal backend for your system

## Network Storage Performance

> **📊 Network Storage Note**: In NFS environments, `fd` often outperforms other backends due to 
> optimized network I/O patterns. For network filesystems, consider forcing the `fd` backend 
> with `DirectoryProfiler(search_backend="fd")` for optimal performance.

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
    profiler = DirectoryProfiler(search_backend=backend_name, show_progress=False)
    
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