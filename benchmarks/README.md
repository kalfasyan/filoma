# Benchmarks

Benchmark filoma performance across different backends and storage types.

## Quick Start

```bash
# Simplest - auto temp dir, medium dataset, auto cleanup
python benchmarks/benchmark.py

# Larger dataset
python benchmarks/benchmark.py --dataset-size large

# Specific path (auto-creates test data)
python benchmarks/benchmark.py --path /tmp/bench

# Network storage benchmark
python benchmarks/benchmark.py --path /mnt/nas/bench --warmup
```

## Usage

```bash
python benchmarks/benchmark.py [OPTIONS]
```

By default, the benchmark:
- Creates a test dataset in a temp directory
- Runs profiling backends (rust, rust-seq, async, fd, python)
- Cleans up after completion

### Options

| Option | Description |
|--------|-------------|
| `--path [LABEL=]PATH` | Directory to benchmark (auto-creates test data if doesn't exist) |
| `--backend BACKEND` | Backend group or specific backend (default: profiling) |
| `-n, --iterations N` | Number of iterations per test (default: 3) |
| `--dataset-size SIZE` | Dataset size: `small`, `medium`, `large`, `xlarge` (default: medium) |
| `--use-existing` | Use existing directory as-is (don't create test data) |
| `--no-cleanup` | Keep generated test data after benchmarking |
| `--clear-cache` | Clear filesystem cache between runs (requires sudo) |
| `--warmup` | Prime NFS cache before benchmarking |
| `--shuffle` | Randomize backend order |
| `-o, --output FILE` | Save results to JSON file |

### Dataset Sizes

| Size | Directories | Files/Dir | Approx Total |
|------|-------------|-----------|--------------|
| small | 10 | 100 | ~1,000 |
| medium | 50 | 200 | ~10,000 |
| large | 100 | 500 | ~50,000 |
| xlarge | 200 | 1000 | ~200,000 |

## Examples

### Basic Benchmark

```bash
# Quick benchmark with defaults
python benchmarks/benchmark.py

# Larger dataset
python benchmarks/benchmark.py --dataset-size large

# Benchmark existing directory (no test data generation)
python benchmarks/benchmark.py --path /usr --use-existing
```

### Compare Storage Types

```bash
# Local vs Network storage comparison
python benchmarks/benchmark.py \
    --path local=/tmp/bench \
    --path nas=/mnt/nas/bench \
    --dataset-size medium
```

### Cold-Cache Benchmark

For accurate benchmarks, clear the filesystem cache between runs (requires sudo):

```bash
python benchmarks/benchmark.py --dataset-size large --clear-cache -n 5
```

### Network Storage Benchmark

Test on network storage with warmup and cache clearing:

```bash
python benchmarks/benchmark.py \
    --path /mnt/nas/bench \
    --dataset-size large \
    --warmup \
    --clear-cache \
    -n 3
```

### Specific Backends

```bash
# Only test Rust backends
python benchmarks/benchmark.py . --backend rust --backend async

# Compare fd vs Rust
python benchmarks/benchmark.py . --backend fd --backend rust
```

## Backend Groups

Backends are organized into groups based on what they measure:

### Profiling Backends (default)

Full directory profiling with metadata collection, extension counting, and statistics.

| Backend | Description |
|---------|-------------|
| `rust` | Rust parallel scanner (rayon) - fastest for local storage |
| `rust-seq` | Rust sequential scanner |
| `async` | Rust async scanner (tokio) - optimized for high-latency network storage |
| `fd` | External fd tool with metadata enrichment |
| `python` | Pure Python implementation |

```bash
# Profiling backends (default)
python benchmarks/benchmark.py --backend profiling
python benchmarks/benchmark.py  # same as above

# Network storage with all options
python benchmarks/benchmark.py \
    --path /mnt/nas/bench \
    --dataset-size xlarge \
    --backend profiling \
    --warmup --shuffle --clear-cache -n 3
```

### Traversal Backends

Fast file/directory traversal only - no metadata collection. Useful for measuring raw filesystem traversal speed.

| Backend | Description |
|---------|-------------|
| `os.walk` | Python standard library |
| `pathlib` | Python pathlib.Path.rglob |
| `rust-fast` | Rust parallel scanner with `fast_path_only` (no metadata) |
| `async-fast` | Rust async scanner with `fast_path_only` (no metadata) |

```bash
# Traversal backends only
python benchmarks/benchmark.py --backend traversal

# Network storage traversal benchmark
python benchmarks/benchmark.py \
    --path /mnt/nas/bench \
    --dataset-size xlarge \
    --backend traversal \
    --warmup --shuffle --clear-cache -n 3
```

### All Backends

```bash
# Run both groups
python benchmarks/benchmark.py --backend all
```

### Mix Individual Backends

```bash
# Compare specific backends
python benchmarks/benchmark.py --backend rust --backend async --backend rust-fast
```

## Sample Output

```
🚀 Filoma Benchmark
======================================================================
Iterations:    3
Cache clear:   No
Backends:      rust, rust-seq, async, fd, python
Targets:       default (/tmp/bench)

📂 Benchmarking: default (/tmp/bench)

======================================================================
📊 Results: default
======================================================================

Method              Avg Time    Files/sec    Speedup      Files
----------------------------------------------------------------------
rust                   0.031s      564,516     (base)     17,500
async                  0.032s      546,875      0.97x     17,500
fd                     0.045s      388,889      0.69x     17,500
rust-seq               0.089s      196,629      0.35x     17,500
python                 0.198s       88,384      0.16x     17,500
```

