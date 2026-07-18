# Installation

`filoma` ships as a regular Python package, so any modern installer works.
We recommend [`uv`](https://docs.astral.sh/uv/) — it's what filoma itself
is developed with — but `pip` works too.

```bash
# Recommended: uv (drops filoma into your project)
uv add filoma

# Or, in a virtualenv / conda env you already activated:
uv pip install filoma

# Classic pip:
pip install filoma
```

> 💡 New to `uv`? Install it once with
> `curl -LsSf https://astral.sh/uv/install.sh | sh`. After that,
> `uv add filoma` and `uv run filoma demo` give you the whole package
>
> - a working dev shell with no virtualenv juggling.

## Performance Tiers

`filoma` is designed to be fast by default and automatically selects the best available backend:

- **🦀 Rust (Fastest)**: Built-in high-performance backend.
- **🔍 fd (Fast)**: Uses the [`fd`](https://github.com/sharkdp/fd) command if available.
- **🐍 Python (Universal)**: Pure Python implementation that works everywhere.

### Optimization (Optional)

Most installs get the Rust backend for free: prebuilt wheels for Python 3.11 on macOS, Linux, and Windows bundle the compiled extension already, so there's nothing to do. If you're on a different Python version or platform, `pip`/`uv` builds the extension from source automatically during install, which needs a Rust toolchain — install one first if that build fails or you land on the fd/Python backend:

```bash
# Install Rust toolchain
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source ~/.cargo/env

# Reinstall filoma so it can build the Rust extension
uv add --reinstall filoma          # uv
pip install --force-reinstall filoma  # pip
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
