# Installation

## Quick Start

```bash
# 🚀 RECOMMENDED: Using uv (modern, fast Python package manager)
uv add filoma

# Traditional method
pip install filoma
```

## Installation Methods

### For uv Projects (Recommended)
```bash
# Install uv first if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Add to your project
uv add filoma
```

### For Scripts or Standalone Use
```bash
uv pip install filoma
```

### Traditional pip
```bash
pip install filoma
```

## Performance Optimization (Optional)

### Option 1: Rust Backend (2.5x faster)
```bash
# Install Rust toolchain
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source ~/.cargo/env

# Reinstall to build Rust extension
uv add filoma --force  # or: pip install --force-reinstall filoma
```

### Option 2: fd Command (Competitive Alternative)
```bash
# Ubuntu/Debian
sudo apt install fd-find

# macOS
brew install fd

# Other systems: https://github.com/sharkdp/fd#installation
```

## Performance Tiers

- **Basic**: Pure Python (works everywhere, ~30K files/sec)
- **Fast**: + fd command (competitive alternative, ~46K files/sec)
- **Fastest**: + Rust backend (best performance, ~70K files/sec, auto-selected)

## Verification

```python
import filoma
from filoma.directories import DirectoryProfiler

print(f"filoma version: {filoma.__version__}")

# Check available backends
profiler = DirectoryProfiler()
print(f"🦀 Rust: {'✅' if profiler.use_rust else '❌'}")
print(f"🔍 fd: {'✅' if profiler.use_fd else '❌'}")

# Quick test
result = profiler.probe(".")
print(f"✅ Found {result['summary']['total_files']} files")
```

## Troubleshooting

### System Directory Issues

When analyzing system directories (like `/`, `/proc`, `/sys`), you might encounter permission errors. filoma handles this gracefully:

```python
from filoma.directories import DirectoryProfiler

# Safe analysis with automatic fallbacks
profiler = DirectoryProfiler()

# This will automatically fall back to Python implementation if Rust fails
result = profiler.probe("/proc", max_depth=2)

# For maximum compatibility with system directories, use Python backend
profiler_safe = DirectoryProfiler(search_backend="python")
result = profiler_safe.probe("/", max_depth=3)
```

### Common Issues

**Permission denied errors:**
```bash
# Run with limited depth to avoid deep system directories
python -c "from filoma.directories import DirectoryProfiler; print(DirectoryProfiler().probe('/', max_depth=2)['summary'])"
```

**Memory issues with large directories:**
```python
# Use fast_path_only for path discovery without metadata
profiler = DirectoryProfiler(fast_path_only=True, build_dataframe=False)
result = profiler.probe("/large/directory")
```

**Progress bar issues in Jupyter:**
Progress bars are automatically disabled in interactive environments (IPython/Jupyter) to avoid conflicts.
