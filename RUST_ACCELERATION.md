# Rust Acceleration for filoma

This document explains how to set up and use the Rust-accelerated directory profiler in filoma.

## Why Rust?

The Rust implementation provides significant performance improvements for directory analysis:

- **Faster filesystem traversal**: Rust's `walkdir` crate is optimized for filesystem operations
- **Efficient memory usage**: Zero-cost abstractions and stack allocation reduce overhead
- **Parallel processing potential**: Rust's safety guarantees make it easier to add parallelization later
- **Type safety**: Compile-time guarantees prevent common bugs

## Expected Performance Gains

Based on typical use cases, you can expect:
- **2-5x faster** for small directories (< 1,000 files)
- **5-10x faster** for medium directories (1,000-10,000 files)  
- **10-20x faster** for large directories (> 10,000 files)

## Setup Instructions

### Understanding uv Installation Methods

Before proceeding, understand which `uv` command to use:

- **`uv add`** → For Python projects with `pyproject.toml` (manages dependencies automatically)
- **`uv pip install`** → For standalone scripts or when you want pip-like behavior
- **`pip install`** → Traditional method for compatibility

> **Tip**: If you're working in a directory with a `pyproject.toml` file, always use `uv add` for proper dependency management.

### Prerequisites

1. **Install Rust** (if not already installed):
   ```bash
   curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
   source ~/.cargo/env
   ```

2. **Install uv** (recommended, faster than pip):
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

3. **Install maturin**:
   ```bash
   # For uv projects (recommended):
   uv add maturin --dev
   
   # For scripts or standalone environments:
   uv pip install maturin
   
   # Traditional method:
   pip install maturin
   ```

### Quick Setup

Run the provided setup script:
```bash
./scripts/setup_rust.sh
```

### Manual Setup

If you prefer manual setup:

1. Build the Rust extension:
   ```bash
   maturin develop
   ```

2. Test the installation:
   ```python
   from filoma.dir import DirectoryProfiler
   profiler = DirectoryProfiler()
   print("Rust acceleration:", "✅ Available" if profiler.use_rust else "❌ Not available")
   ```

## Usage

The hybrid profiler automatically uses Rust when available, falling back to Python otherwise:

```python
from filoma.dir import DirectoryProfiler

# Uses Rust by default (if available)
profiler = DirectoryProfiler()
result = profiler.analyze("/path/to/directory")

# Force Python implementation
python_profiler = DirectoryProfiler(use_rust=False)
result = python_profiler.analyze("/path/to/directory")

# The API is identical - all existing code works unchanged!
profiler.print_report(result)
```

## Benchmarking

Run the included benchmark to see performance improvements on your system:

```bash
python scripts/benchmark.py
```

This will create a test directory structure and compare both implementations.

## Current Status

**Implemented:**
- ✅ Core directory traversal in Rust
- ✅ File counting and size calculation
- ✅ Extension analysis
- ✅ Empty directory detection
- ✅ Depth statistics
- ✅ Hybrid Python/Rust API

**TODO for v2:**
- [ ] Parallel directory traversal
- [ ] Memory-mapped file reading for large files
- [ ] Advanced pattern matching in Rust
- [ ] Custom file filters
- [ ] Progress reporting for large directories

## Troubleshooting

### "Rust implementation not available"

This usually means:
1. Rust is not installed
2. The extension wasn't built (run `maturin develop`)
3. Build failed due to missing dependencies

### Build Errors

Common issues:
- **Missing Rust**: Install Rust toolchain
- **Permission errors**: Ensure you have write permissions
- **Old maturin**: Update with `uv pip install -U maturin` or `pip install -U maturin`

### Performance Not as Expected

- Ensure you're testing on large enough directories (> 1,000 files)
- Check if you're running in debug mode (use `maturin develop --release`)
- Cold vs warm filesystem cache can affect results

## Contributing

To contribute to the Rust implementation:

1. The Rust code is in `src/lib.rs`
2. Build with `maturin develop` for testing
3. Run `python scripts/benchmark.py` to verify performance
4. All changes should maintain API compatibility

## Technical Details

The Rust extension:
- Uses PyO3 for Python bindings
- Leverages `walkdir` for efficient filesystem traversal
- Returns data structures compatible with the Python implementation
- Handles errors gracefully (permissions, broken symlinks, etc.)
- Maintains the same output format as the Python version
