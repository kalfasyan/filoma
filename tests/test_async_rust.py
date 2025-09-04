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


def make_sample_tree(root):
    os.makedirs(os.path.join(root, "dir1"), exist_ok=True)
    os.makedirs(os.path.join(root, "dir2", "sub"), exist_ok=True)
    with open(os.path.join(root, "file1.txt"), "w") as f:
        f.write("hello")
    with open(os.path.join(root, "dir1", "file2.log"), "w") as f:
        f.write("log")
    with open(os.path.join(root, "dir2", "sub", "file3.md"), "w") as f:
        f.write("md")


@pytest.mark.skipif(not ASYNC_AVAILABLE, reason="Async Rust prober not available")
def test_async_matches_sync():
    tmp = tempfile.mkdtemp(prefix="filoma-test-")
    try:
        make_sample_tree(tmp)

        # Use DirectoryProfiler to get Rust sync analysis
        profiler = DirectoryProfiler(use_rust=True, use_parallel=False, show_progress=False)
        sync_result = profiler.probe(tmp)

        # Call async Rust prober directly
        async_result = probe_directory_rust_async(tmp, None, 8, 1000, 0, False)

        assert sync_result["summary"]["total_files"] == async_result["summary"]["total_files"]
        assert sync_result["summary"]["total_folders"] == async_result["summary"]["total_folders"]
    finally:
        shutil.rmtree(tmp)
