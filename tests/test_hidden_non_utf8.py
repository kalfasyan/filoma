"""Hidden-name filtering must also apply to names that are not valid UTF-8 (Unix only)."""

import os
import sys

import pytest

core = pytest.importorskip("filoma.filoma_core")

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="only Linux filesystems accept arbitrary non-UTF-8 names")

# Each engine takes (path, search_hidden) and returns the same summary shape.
ENGINES = {
    "walkdir-sequential": lambda p, hidden: core.probe_directory_rust(p, search_hidden=hidden, return_paths=True),
    "walkdir-parallel": lambda p, hidden: core.probe_directory_rust_parallel(p, parallel_threshold=0, search_hidden=hidden, return_paths=True),
    "dua-core": lambda p, hidden: core.probe_directory_rust_dua_core(p, search_hidden=hidden, return_paths=True),
    "async": lambda p, hidden: core.probe_directory_rust_async(p, search_hidden=hidden, return_paths=True, concurrency_limit=4),
}


@pytest.fixture
def non_utf8_tree(tmp_path):
    """A root with one visible and one hidden folder whose names are not valid UTF-8."""
    (tmp_path / "visible.txt").write_text("v")
    (tmp_path / os.fsdecode(b"d\xff")).mkdir()
    (tmp_path / os.fsdecode(b"d\xff") / "inner.txt").write_text("i")
    (tmp_path / "v").mkdir()
    (tmp_path / "v" / "a.txt").write_text("a")
    (tmp_path / os.fsdecode(b".h\xff")).mkdir()
    (tmp_path / os.fsdecode(b".h\xff") / "hidden.txt").write_text("h")
    return tmp_path


# Known gap: the dua-core and async engines key folders by their (String) path, so folders whose
# names are not valid UTF-8 are not counted at all. The walkdir engines count them. Strict xfail, so
# the test starts failing (XPASS) once the gap is fixed and the marker can be removed.
NON_UTF8_FOLDER_GAP = pytest.mark.xfail(
    strict=True,
    reason="dua-core and async skip folders whose names are not valid UTF-8 (String-based paths); see known limitations",
)


def engine_params():
    return [pytest.param(name, marks=NON_UTF8_FOLDER_GAP) if name in ("dua-core", "async") else name for name in sorted(ENGINES)]


@pytest.mark.parametrize("engine", engine_params())
def test_non_utf8_folders_are_counted(engine, non_utf8_tree):
    """Folders whose names are not valid UTF-8 count toward folder totals and paths, like the Python backend."""
    summary = ENGINES[engine](str(non_utf8_tree), True)["summary"]

    assert summary["total_folders"] == 4  # root, d\xff, v, .h\xff
    assert summary["total_files"] == 4


@pytest.mark.parametrize("engine", engine_params())
def test_non_utf8_hidden_folders_are_skipped_when_search_hidden_is_off(engine, non_utf8_tree):
    """A hidden folder with a non-UTF-8 name is pruned with its contents, and visible non-UTF-8 folders still count."""
    summary = ENGINES[engine](str(non_utf8_tree), False)["summary"]

    assert summary["total_folders"] == 3  # root, d\xff, v
    assert summary["total_files"] == 3


def test_dua_core_skips_hidden_non_utf8_file_when_search_hidden_is_off(tmp_path):
    (tmp_path / os.fsdecode(b".env\xff")).write_text("secret")
    (tmp_path / "visible.txt").write_text("y")

    hidden_off = core.probe_directory_rust_dua_core(str(tmp_path), max_depth=None, search_hidden=False, return_paths=True)
    hidden_on = core.probe_directory_rust_dua_core(str(tmp_path), max_depth=None, search_hidden=True, return_paths=True)

    assert hidden_off["summary"]["total_files"] == 1
    assert hidden_on["summary"]["total_files"] == 2
