# Backend Architecture

`filoma` provides multiple high-performance backends that automatically select the best option for your system.

## Backend Overview

### 🐍 Python Backend (Universal)

- **Always available** - works on any Python installation
- **Full compatibility** - complete feature set
- **Reliable fallback** - when other backends aren't available

### 🦀 Rust Backend (Fastest for Local Storage)

- **Best performance** - 2.5x+ faster than alternatives on local storage
- **Parallel processing** - dua-core walker by default (parallel `read_dir` + parallel metadata); walkdir engines as fallback
- **Auto-selected** - chosen by default when available for local filesystems
- **Engine switch** - `walker="auto" | "dua-core" | "walkdir"` in `DirectoryProfilerConfig`; `walker_threads` tunes the worker count
- **Same API** - drop-in replacement with identical output

### ⚡ Async Backend (Network-optimized)

- **Network optimized** - tokio-based with bounded concurrency, timeouts, and retries
- **Opt-in** - enabled with `use_async=True` (default `False`); useful for NFS, SMB, CIFS
- **Tunable concurrency** - `network_concurrency`, `network_timeout_ms`, `network_retries` parameters

### 🔍 fd Backend (Competitive Alternative)

- **Fast file discovery** - leverages the `fd` command-line tool
- **Advanced patterns** - supports regex and glob patterns
- **Hybrid approach** - fd for discovery + Python for analysis
- **Network alternative** - viable option for network filesystems

## Automatic Selection

```python
from filoma.directories import DirectoryProfiler, DirectoryProfilerConfig

# Automatically uses fastest available backend
profiler = DirectoryProfiler(DirectoryProfilerConfig())
result = profiler.probe("/path/to/directory")

# Check which backend was used
profiler.print_summary(result)
# Shows: "Directory Analysis: /path (🦀 Rust)" or "🔍 fd" or "🐍 Python"
```

### 🦀 Rust Async (Network-optimized)

- **When**: Used for network-mounted filesystems (NFS/CIFS/SMB/Gluster/SSHFS) when `use_async=True` and the tokio build is available. Without it, network mounts use the regular Rust engines.
- **Why**: Uses a tokio-based scanner with bounded concurrency to hide network latency and avoid overwhelming remote servers.
- **Tuning**: `DirectoryProfiler` accepts network tuning parameters:
  - `network_concurrency` (int): maximum outstanding directory ops (default 64)
  - `network_timeout_ms` (int): per-operation timeout in milliseconds (default 5000)
  - `network_retries` (int): number of retries on transient failures (default 0)

Use these to tune behavior on slow or flaky mounts. Example:

```python
profiler = DirectoryProfiler(DirectoryProfilerConfig(network_concurrency=32, network_timeout_ms=2000, network_retries=1))
```

If the async Rust backend isn't compiled into your wheel, filoma will fall back to the existing Rust or fd backends.

## Manual Backend Selection

```python
# Force specific backend
profiler_rust = DirectoryProfiler(DirectoryProfilerConfig(search_backend="rust"))
profiler_fd = DirectoryProfiler(DirectoryProfilerConfig(search_backend="fd"))
profiler_python = DirectoryProfiler(DirectoryProfilerConfig(search_backend="python"))

# Force the traversal engine inside the Rust backend
profiler_dua = DirectoryProfiler(DirectoryProfilerConfig(search_backend="rust", walker="dua-core"))
profiler_walkdir = DirectoryProfiler(DirectoryProfilerConfig(search_backend="rust", walker="walkdir"))

# Check availability
print(f"Rust available: {profiler_rust.is_rust_available()}")
print(f"fd available: {profiler_fd.is_fd_available()}")
print(f"Python available: True")  # Always available
```

## Backend Comparison

```python
import time

backends = ["rust", "fd", "python"]
for backend in backends:
    profiler = DirectoryProfiler(DirectoryProfilerConfig(search_backend=backend, show_progress=False))
    # Check if the specific backend is available
    if ((backend == "rust" and profiler.is_rust_available()) or
        (backend == "fd" and profiler.is_fd_available()) or
        (backend == "python")):  # Python always available
        start = time.time()
        result = profiler.probe("/test/directory")
        elapsed = time.time() - start
        files_per_sec = result['summary']['total_files'] / elapsed
        print(f"{backend}: {elapsed:.3f}s ({files_per_sec:,.0f} files/sec)")
```

## When to Use Each Backend

| Use Case                       | Recommended Backend                    | Why                                                                |
| ------------------------------ | -------------------------------------- | ------------------------------------------------------------------ |
| **Large local directories**    | Auto (Rust preferred)                  | Best overall performance for local storage                         |
| **Network filesystems (NFS)**  | Auto, or `use_async=True` for timeouts | Async backend handles high latency and flaky mounts                |
| **CI/CD environments**         | Auto                                   | Reliable with graceful fallbacks                                   |
| **Maximum compatibility**      | `python`                               | Always works, no dependencies                                      |
| **DataFrame analysis**         | Auto (Rust)                            | Engine paths feed the DataFrame — no second traversal              |
| **Pattern matching**           | `fd`                                   | Advanced regex/glob support                                        |
| **Tuning network performance** | `use_async=True` with config           | Use `network_concurrency`, `network_timeout_ms`, `network_retries` |

## Technical Details

All backends provide:

- **Identical APIs** - same function signatures and parameters
- **Same output format** - consistent data structures
- **Progress bars** - real-time feedback for large operations
- **Error handling** - graceful fallbacks and error reporting

### Performance Characteristics

- **Rust**: Best for CPU-intensive operations, parallel processing
- **fd**: Best for I/O-intensive operations, pattern matching
- **Python**: Most compatible, good baseline performance

### Backend Detection

```python
from filoma.directories import DirectoryProfiler
from filoma.core import FdIntegration

# Check what's available
profiler = DirectoryProfiler(DirectoryProfilerConfig())
fd = FdIntegration()

print("Available backends:")
print(f"  🐍 Python: Always available")
print(f"  🦀 Rust: {'✅' if profiler.use_rust else '❌'}")
print(f"  🔍 fd: {'✅' if fd.is_available() else '❌'}")

if fd.is_available():
    print(f"  fd version: {fd.get_version()}")
```
