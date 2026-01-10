# Installation

The simplest way to install `filoma` is via `pip`:

```bash
pip install filoma
```

## Performance Tiers

`filoma` is designed to be fast by default and automatically selects the best available backend:

- **🦀 Rust (Fastest)**: Built-in high-performance backend.
- **🔍 fd (Fast)**: Uses the [`fd`](https://github.com/sharkdp/fd) command if available.
- **🐍 Python (Universal)**: Pure Python implementation that works everywhere.

### Optimization (Optional)

To ensure you have the **Fastest (Rust)** backend active, you should have the Rust toolchain installed when installing `filoma` so it can compile the extension:

```bash
# Install Rust toolchain
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source ~/.cargo/env

# Install/Reinstall filoma
pip install --force-reinstall filoma
```

Alternatively, installing `fd` provides a great performance boost without needing a compiler:

```bash
# Ubuntu/Debian
sudo apt install fd-find

# macOS
brew install fd
```

## Verification

You can verify your installation and see which backends are active with this snippet:

```python
import filoma
from filoma.directories import DirectoryProfiler, DirectoryProfilerConfig

print(f"filoma version: {filoma.__version__}")

# Check which backend is actually being used
# Note: 'auto' selection prefers Rust over fd for maximum performance.
# If both are available, Rust will show ✅ and fd will show ❌.
profiler = DirectoryProfiler(DirectoryProfilerConfig())
print(f"🦀 Rust (Active): {'✅' if profiler.use_rust else '❌'}")
print(f"🔍 fd (Active):   {'✅' if profiler.use_fd else '❌'}")

# To check if fd is available even if not active:
from filoma.core import FdIntegration
print(f"🔍 fd (Installed): {'✅' if FdIntegration().is_available() else '❌'}")

# Quick test
from filoma import probe
result = probe('.')
print(f"✅ Found {result['summary']['total_files']} files using {result['timing']['implementation']}")
```

## Troubleshooting

### System Directory Issues

When analyzing system directories (like `/`, `/proc`, `/sys`), you might encounter permission errors. `filoma` handles this gracefully:

```python
from filoma.directories import DirectoryProfiler, DirectoryProfilerConfig

# Safe analysis with automatic fallbacks
profiler = DirectoryProfiler(DirectoryProfilerConfig())

# This will automatically fall back to Python implementation if Rust fails
result = profiler.probe("/proc", max_depth=2)

# For maximum compatibility with system directories, use Python backend
profiler_safe = DirectoryProfiler(DirectoryProfilerConfig(search_backend="python"))
result = profiler_safe.probe("/", max_depth=3)
```

### Common Issues

**Permission denied errors:**
```bash
# Run with limited depth to avoid deep system directories
python -c "from filoma import probe; print(probe('/', max_depth=2)['summary'])"
```

**Memory issues with large directories:**
```python
# Use fast_path_only for path discovery without metadata
profiler = DirectoryProfiler(DirectoryProfilerConfig(fast_path_only=True, build_dataframe=False))
result = profiler.probe("/large/directory")
```
