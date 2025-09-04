import os
import shutil
import tempfile

import pytest

from filoma.directories import DirectoryProfiler

try:
    from filoma.filoma_core import probe_directory_rust_async

    ASYNC_AVAILABLE = True
except Exception:
    ASYNC_AVAILABLE = False


@pytest.mark.skipif(not ASYNC_AVAILABLE, reason="Async Rust prober not available")
def run_parity(root):
    profiler = DirectoryProfiler(use_rust=True, use_parallel=False, show_progress=False)
    sync_result = profiler.probe(root)
    # Use smaller concurrency/timeout for faster tests
    async_result = probe_directory_rust_async(root, None, 4, 200, 0, False)
    assert sync_result["summary"]["total_files"] == async_result["summary"]["total_files"]
    assert sync_result["summary"]["total_folders"] == async_result["summary"]["total_folders"]


@pytest.mark.skipif(not ASYNC_AVAILABLE, reason="Async Rust prober not available")
def test_empty_root_parity():
    tmp = tempfile.mkdtemp(prefix="filoma-test-empty-")
    try:
        run_parity(tmp)
    finally:
        shutil.rmtree(tmp)


@pytest.mark.skipif(not ASYNC_AVAILABLE, reason="Async Rust prober not available")
def test_single_file_parity():
    tmp = tempfile.mkdtemp(prefix="filoma-test-single-")
    try:
        with open(os.path.join(tmp, "only.txt"), "w") as f:
            f.write("x")
        run_parity(tmp)
    finally:
        shutil.rmtree(tmp)


@pytest.mark.skipif(not ASYNC_AVAILABLE, reason="Async Rust prober not available")
def test_deep_nesting_parity():
    tmp = tempfile.mkdtemp(prefix="filoma-test-deep-")
    try:
        cur = tmp
        # shallower depth for faster test runs
        for i in range(2):
            cur = os.path.join(cur, f"d{i}")
            os.makedirs(cur, exist_ok=True)
        with open(os.path.join(cur, "deep.txt"), "w") as f:
            f.write("deep")
        run_parity(tmp)
    finally:
        shutil.rmtree(tmp)
