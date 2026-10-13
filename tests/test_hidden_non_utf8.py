"""Hidden-name filtering must also apply to names that are not valid UTF-8 (Unix only)."""

import os
import sys

import pytest

core = pytest.importorskip("filoma.filoma_core")

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="non-UTF-8 file names are a Unix concept")


def test_dua_core_skips_hidden_non_utf8_file_when_search_hidden_is_off(tmp_path):
    (tmp_path / os.fsdecode(b".env\xff")).write_text("secret")
    (tmp_path / "visible.txt").write_text("y")

    hidden_off = core.probe_directory_rust_dua_core(str(tmp_path), max_depth=None, search_hidden=False, return_paths=True)
    hidden_on = core.probe_directory_rust_dua_core(str(tmp_path), max_depth=None, search_hidden=True, return_paths=True)

    assert hidden_off["summary"]["total_files"] == 1
    assert hidden_on["summary"]["total_files"] == 2
