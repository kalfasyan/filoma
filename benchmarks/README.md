# Benchmarks

Benchmark filoma performance across different backends and storage types.

## Quick Start

```bash
# Benchmark current directory
python benchmarks/benchmark.py .

# Benchmark with generated test data
python benchmarks/benchmark.py --path /tmp/bench --setup-dataset

# Full benchmark with multiple iterations
python benchmarks/benchmark.py --path /tmp/bench --setup-dataset --iterations 5
```

## Usage

```bash
python benchmarks/benchmark.py [PATH] [OPTIONS]
```

### Options

| Option | Description |
|--------|-------------|
| `PATH` | Directory to benchmark (positional) |
| `--path [LABEL=]PATH` | Labeled path (can repeat for comparisons) |
| `--backend BACKEND` | Backend to test: `os.walk`, `pathlib`, `rust`, `rust-seq`, `async`, `fd`, `python`, `all` |
| `-n, --iterations N` | Number of iterations per test (default: 3) |
| `--setup-dataset` | Create test dataset in target directories |
| `--dataset-size SIZE` | Dataset size: `small`, `medium`, `large`, `xlarge` |
| `--clear-cache` | Clear filesystem cache between runs (requires sudo) |
| `--no-ignore` | Ignore .gitignore files for fair comparison |
| `--cleanup` | Delete test directories after benchmarking |
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
# Benchmark an existing directory
python benchmarks/benchmark.py /usr

# Benchmark with generated test data
python benchmarks/benchmark.py --path /tmp/bench --setup-dataset --dataset-size large
```

### Compare Storage Types

```bash
# Local vs Network storage comparison
python benchmarks/benchmark.py \
    --path local=/tmp/bench \
    --path nas=/mnt/nas/bench \
    --setup-dataset \
    --dataset-size medium
```

### Cold-Cache Benchmark

For accurate benchmarks, clear the filesystem cache between runs (requires sudo):

```bash
python benchmarks/benchmark.py --path /data --iterations 5 --clear-cache
```

### Network Storage - All Backends

Test all backends on network storage with cache clearing for accurate results:

```bash
uv run python benchmarks/benchmark.py \
    --path /mnt/nas/bench-test \
    --setup-dataset \
    --dataset-size large \
    --backend all \
    --clear-cache \
    -n 3 \
    --cleanup
```

### Specific Backends

```bash
# Only test Rust backends
python benchmarks/benchmark.py . --backend rust --backend async

# Compare fd vs Rust
python benchmarks/benchmark.py . --backend fd --backend rust
```

## Backends

| Backend | Description |
|---------|-------------|
| `os.walk` | Python standard library (baseline) |
| `pathlib` | Python pathlib.Path.rglob |
| `rust` | Rust parallel scanner (rayon) |
| `rust-seq` | Rust sequential scanner |
| `async` | Rust async scanner (tokio) - optimized for network storage |
| `fd` | External fd tool |
| `python` | Pure Python implementation |

## Sample Output

```
🚀 Filoma Benchmark
======================================================================
Iterations:    3
Cache clear:   No
Backends:      os.walk, pathlib, rust, rust-seq, async, fd, python
Targets:       default (/tmp/bench)

📂 Benchmarking: default (/tmp/bench)

======================================================================
📊 Results: default
======================================================================

Method              Avg Time    Files/sec    Speedup      Files
----------------------------------------------------------------------
rust                   0.031s      564,516      5.23x     17,500
async                  0.032s      546,875      5.06x     17,500
fd                     0.045s      388,889      3.60x     17,500
rust-seq               0.089s      196,629      1.82x     17,500
pathlib                0.142s      123,239      1.14x     17,500
os.walk                0.162s      108,025      (base)    17,500
python                 0.198s       88,384      0.82x     17,500
```

