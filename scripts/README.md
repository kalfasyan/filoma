# Scripts Directory

This directory contains development and utility scripts for the filoma project.

## Scripts

- **`benchmark.py`** - Performance benchmark comparing Python vs Rust implementations
  ```bash
  python scripts/benchmark.py
  ```

- **`test_parallel.py`** - Performance testing script for parallel implementations
  ```bash
  python scripts/test_parallel.py
  ```

- **`setup_rust.sh`** - Automated setup script for Rust acceleration
  ```bash
  ./scripts/setup_rust.sh
  ```

- **`bump_version.py`** - Version bumping utility (used by Makefile)
  ```bash
  python scripts/bump_version.py [patch|minor|major]
  ```

- **`release.sh`** - Release automation script (used by Makefile)
  ```bash
  ./scripts/release.sh [patch|minor|major]
  ```

## Usage

Most scripts are intended to be run from the project root directory:

```bash
# From project root
python scripts/benchmark.py
python scripts/test_parallel.py
./scripts/setup_rust.sh

# Or use the Makefile targets
make version
make benchmark
make release-patch
```
