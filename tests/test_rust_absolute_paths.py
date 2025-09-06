import os
import shutil
import tempfile
from pathlib import Path

import pytest

# No top-level imports from DirectoryProfiler needed; we call Rust prober directly


def _rust_core_available():
    try:

        return True
    except Exception:
        return False


@pytest.mark.skipif(not _rust_core_available(), reason="Rust backend not available")
def test_rust_returns_absolute_paths_and_canonicalizes_with_follow_links():
    tmp = tempfile.mkdtemp(prefix="filoma-test-abs-")
    try:
        tmp_path = Path(tmp)

        # Create an external real directory and a symlink inside tmp pointing to it
        external = tempfile.mkdtemp(prefix="filoma-external-")
        external_path = Path(external)
        (external_path / "target.txt").write_text("content")

        # Inside tmp create a symlink named 'real' that points to the external directory
        real_link = tmp_path / "real"
        os.symlink(str(external_path), str(real_link))

        # Probe without following links: call Rust prober directly with follow_links=False
        from filoma.filoma_core import probe_directory_rust

        result_no_follow = probe_directory_rust(str(tmp_path), None, False, follow_links=False, search_hidden=False, no_ignore=False)

        # The Rust prober returns a 'top_folders_by_file_count' which contains
        # folder path strings; validate those are absolute and point under tmp
        top_folders = result_no_follow.get("top_folders_by_file_count", [])
        assert top_folders, "No folder counts returned by Rust prober"

        folder_paths = [fp for fp, _count in top_folders]
        for p in folder_paths:
            assert os.path.isabs(p), f"Folder path is not absolute: {p}"
            assert os.path.commonpath([p, str(tmp_path)]) == str(tmp_path)

        # Now probe with follow_links=True: the symlinked 'real' directory should be canonicalized
        result_follow = probe_directory_rust(str(tmp_path), None, False, follow_links=True, search_hidden=False, no_ignore=False)

        top_folders_follow = result_follow.get("top_folders_by_file_count", [])
        folder_paths_follow = [fp for fp, _ in top_folders_follow]

        # The canonical external path should appear in the follow-results
        canonical_external = os.path.realpath(str(external_path))
        assert any(os.path.realpath(p) == canonical_external for p in folder_paths_follow), (
            "Canonical external path not present when follow_links=True"
        )

        # Cleanup external tempdir
        shutil.rmtree(external)

    finally:
        shutil.rmtree(tmp)
