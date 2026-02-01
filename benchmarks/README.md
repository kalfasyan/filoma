# Benchmark Scripts

This directory contains benchmark scripts to compare `filoma` performance against standard Python alternatives.

## Quick Start

```bash
# Run benchmark with default settings (creates temp test directory)
python benchmarks/benchmark_comparison.py

# Benchmark an existing directory
python benchmarks/benchmark_comparison.py --path /path/to/directory

# More iterations for better accuracy
python benchmarks/benchmark_comparison.py --iterations 5
```

## Benchmark Scripts

### `benchmark_comparison.py`

Comprehensive benchmark comparing:
- `os.walk()` - Standard library directory walking
- `pathlib.Path.rglob()` - Modern Python pathlib approach
- `filoma` with different backends:
  - Auto (selects best available)
  - Rust backend
  - `fd` backend
  - Python backend

**Features:**
- ✅ Cold cache testing (clears filesystem cache between runs)
- ✅ Multiple iterations for statistical accuracy
- ✅ Configurable test directory structure
- ✅ Detailed performance statistics

**Usage:**

```bash
# Basic usage
python benchmarks/benchmark_comparison.py

# Benchmark existing directory
python benchmarks/benchmark_comparison.py --path /usr

# Custom test structure
python benchmarks/benchmark_comparison.py \
    --num-dirs 200 \
    --files-per-dir 100 \
    --max-depth 4 \
    --iterations 5

# Skip cache clearing (faster, but less realistic)
python benchmarks/benchmark_comparison.py --no-clear-cache

# Keep temporary test directory for inspection
python benchmarks/benchmark_comparison.py --keep-temp
```

## Cold Cache Testing

For accurate, realistic benchmarks, the script clears the OS filesystem cache between runs. This requires `sudo` privileges:

```bash
# Run with sudo for accurate cold-cache benchmarks
sudo python benchmarks/benchmark_comparison.py
```

Without sudo, the script will still run but will warn that results may be affected by OS caching.

### Why Cold Cache Matters

Filesystem caching can make benchmarks **2-8x faster** than real-world performance:
- **Warm cache**: Filesystem metadata is cached in memory → very fast
- **Cold cache**: First-time access, realistic for real-world usage → slower but accurate

The benchmark script uses cold cache methodology to represent realistic performance.

## Understanding Results

The benchmark reports:
- **Average time**: Mean execution time across iterations
- **Min/Max**: Best and worst case times
- **Standard deviation**: Consistency of results
- **Speedup**: Relative performance vs baseline (`os.walk`)

### Example Output

```
📈 BENCHMARK RESULTS SUMMARY
================================================================================
Test directory: /tmp/filoma_benchmark_xyz

Method                    Avg Time     Files/sec   Speedup
--------------------------------------------------------------------------------
filoma (rust)               0.234s                   8.50x
filoma (auto)               0.245s                   8.12x
filoma (fd)                 0.312s                   6.38x
pathlib.rglob               0.856s                   2.33x
os.walk                     1.992s                   1.00x
filoma (python)             2.145s                   0.93x
```

## Benchmark Methodology

1. **Test Structure Creation**: Generates a realistic directory tree with configurable depth and file counts
2. **Cache Clearing**: Clears OS filesystem cache between iterations (requires sudo)
3. **Multiple Iterations**: Runs each method multiple times and averages results
4. **Statistical Analysis**: Calculates mean, min, max, and standard deviation

## Tips for Accurate Benchmarks

1. **Use sudo**: For accurate cold-cache results
2. **Multiple iterations**: Use `--iterations 5` or more for statistical significance
3. **Test on target storage**: Results vary by filesystem type (SSD vs HDD vs NFS)
4. **Avoid system load**: Run when system is idle for consistent results
5. **Large test sets**: Use `--num-dirs` and `--files-per-dir` to create realistic workloads

## Interpreting Results

- **filoma (rust)**: Fastest option when Rust backend is available
- **filoma (fd)**: Excellent performance, especially on network filesystems
- **filoma (python)**: Fallback option, similar to `os.walk` performance
- **pathlib.rglob**: Modern Python approach, typically faster than `os.walk`
- **os.walk**: Baseline for comparison

Performance characteristics:
- **Local SSD**: Rust > fd > pathlib > os.walk
- **Network filesystem (NFS)**: fd > Rust > pathlib > os.walk
- **HDD**: Rust > fd > pathlib > os.walk

## Troubleshooting

**"Could not clear filesystem cache"**
- Run with `sudo` for accurate cold-cache benchmarks
- Or use `--no-clear-cache` flag (results will be faster due to caching)

**"Backend not available"**
- Rust backend requires compiled extension module
- `fd` backend requires `fd` command installed
- Python backend always available as fallback

**Slow benchmark execution**
- Cache clearing adds overhead; use `--no-clear-cache` for faster runs
- Reduce `--iterations` for quicker results
- Use smaller test structures (`--num-dirs`, `--files-per-dir`)

