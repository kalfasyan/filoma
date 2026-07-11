"""Tests for the pure-Python fallback in :class:`FdFinder`.

These tests intentionally force ``FdIntegration.is_available`` to return
``False`` so that the Python fallback paths are exercised regardless of
whether the ``fd`` binary is installed on the host running the test suite.
"""

import os
import time
from pathlib import Path

import pytest

from filoma.directories.fd_finder import FdFinder


@pytest.fixture
def fake_unavailable_fd(monkeypatch):
    """Make `FdIntegration.is_available` always return False."""
    monkeypatch.setattr(
        "filoma.core.fd_integration.FdIntegration.is_available",
        lambda self: False,
    )
    yield


@pytest.fixture
def sample_tree(tmp_path: Path) -> Path:
    """Create a small directory tree with Python, Markdown, and ignored files."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('hi')\n")
    (tmp_path / "src" / "util.py").write_text("def f(): pass\n")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "readme.md").write_text("# Hello\n")
    (tmp_path / "docs" / "guide.md").write_text("# Guide\n")
    (tmp_path / "deep").mkdir()
    (tmp_path / "deep" / "nested").mkdir()
    (tmp_path / "deep" / "nested" / "deeper.py").write_text("# nested\n")
    (tmp_path / ".hidden.py").write_text("# hidden\n")
    (tmp_path / ".secret").mkdir()
    (tmp_path / ".secret" / "shh.py").write_text("# in hidden dir\n")
    # Default-ignored cache directory should be skipped.
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "x.py").write_text("# cached\n")
    return tmp_path


def test_find_files_fallback_finds_py_files(fake_unavailable_fd, sample_tree):
    finder = FdFinder()
    assert finder.is_available() is False

    py_files = finder.find_files(pattern=r"\.py$", path=sample_tree)
    names = sorted(Path(p).name for p in py_files)
    # Hidden files and __pycache__ entries are excluded by default.
    assert names == ["deeper.py", "main.py", "util.py"]


def test_find_files_glob_fallback(fake_unavailable_fd, sample_tree):
    finder = FdFinder()
    py_files = finder.find_files(pattern="*.py", path=sample_tree, use_glob=True)
    assert {Path(p).name for p in py_files} == {"main.py", "util.py", "deeper.py"}


def test_find_files_case_insensitive_fallback(fake_unavailable_fd, sample_tree):
    finder = FdFinder()
    files = finder.find_files(pattern="README", path=sample_tree, case_sensitive=False)
    assert any(Path(p).name == "readme.md" for p in files)


def test_find_by_extension_fallback(fake_unavailable_fd, sample_tree):
    finder = FdFinder()
    py_files = finder.find_by_extension(["py"], path=sample_tree)
    md_files = finder.find_by_extension(".md", path=sample_tree)
    assert len(py_files) == 3  # main.py, util.py, deeper.py (ignores hidden + __pycache__)
    assert {Path(p).name for p in md_files} == {"readme.md", "guide.md"}


def test_find_directories_fallback(fake_unavailable_fd, sample_tree):
    finder = FdFinder()
    dirs = finder.find_directories(pattern="^nested$", path=sample_tree)
    assert any(Path(d).name == "nested" for d in dirs)


def test_count_files_fallback(fake_unavailable_fd, sample_tree):
    finder = FdFinder()
    count = finder.count_files(pattern=r"\.py$", path=sample_tree)
    assert count == 3


def test_get_stats_fallback(fake_unavailable_fd, sample_tree):
    finder = FdFinder()
    stats = finder.get_stats(path=sample_tree)
    assert stats["backend"] == "python"
    # 5 visible files: main.py, util.py, readme.md, guide.md, deeper.py
    assert stats["file_count"] == 5
    # 3 visible directories: src, docs, deep, deep/nested  -> at least 3
    assert stats["directory_count"] >= 3


def test_max_depth_fallback(fake_unavailable_fd, sample_tree):
    finder = FdFinder()
    shallow = finder.find_files(pattern=r"\.py$", path=sample_tree, max_depth=1)
    # max_depth=1 means top-level only, so deeper.py at depth 3 must be excluded.
    names = {Path(p).name for p in shallow}
    assert "deeper.py" not in names


def test_hidden_flag_fallback(fake_unavailable_fd, sample_tree):
    finder = FdFinder()
    visible = finder.find_files(pattern=r"\.py$", path=sample_tree)
    with_hidden = finder.find_files(pattern=r"\.py$", path=sample_tree, hidden=True)
    visible_names = {Path(p).name for p in visible}
    hidden_names = {Path(p).name for p in with_hidden}
    assert ".hidden.py" not in visible_names
    assert ".hidden.py" in hidden_names


def test_no_ignore_flag_fallback(fake_unavailable_fd, sample_tree):
    finder = FdFinder()
    default = finder.find_files(pattern=r"\.py$", path=sample_tree)
    keep_caches = finder.find_files(pattern=r"\.py$", path=sample_tree, no_ignore=True)
    default_paths = {str(p) for p in default}
    keep_paths = {str(p) for p in keep_caches}
    assert not any("__pycache__" in p for p in default_paths)
    assert any("__pycache__" in p for p in keep_paths)


def test_find_large_files_fallback(fake_unavailable_fd, tmp_path: Path):
    big = tmp_path / "big.bin"
    small = tmp_path / "small.bin"
    big.write_bytes(b"\x00" * 2048)
    small.write_bytes(b"\x00" * 16)

    finder = FdFinder()
    results = finder.find_large_files(path=tmp_path, min_size="1k")
    names = {Path(p).name for p in results}
    assert "big.bin" in names
    assert "small.bin" not in names


def test_find_recent_files_fallback(fake_unavailable_fd, tmp_path: Path):
    new = tmp_path / "new.txt"
    old = tmp_path / "old.txt"
    new.write_text("new")
    old.write_text("old")
    # Backdate the "old" file so it falls outside a short window.
    past = time.time() - 7 * 24 * 3600
    os.utime(old, (past, past))

    finder = FdFinder()
    results = finder.find_recent_files(path=tmp_path, changed_within="1h")
    names = {Path(p).name for p in results}
    assert "new.txt" in names
    assert "old.txt" not in names


def test_find_empty_directories_fallback(fake_unavailable_fd, tmp_path: Path):
    (tmp_path / "empty_dir").mkdir()
    populated = tmp_path / "populated"
    populated.mkdir()
    (populated / "f.txt").write_text("x")

    finder = FdFinder()
    results = finder.find_empty_directories(path=tmp_path)
    names = {Path(p).name for p in results}
    assert "empty_dir" in names
    assert "populated" not in names


def test_filaraki_search_files_works_without_fd(fake_unavailable_fd, sample_tree, monkeypatch):
    """The Filaraki agent's ``search_files`` tool must report a non-zero count."""
    # Avoid loading polars-based enrichment if it's slow during the test.
    from filoma.filaraki import tools

    class FakeDeps:
        def __init__(self):
            self.current_df = None

    class FakeCtx:
        def __init__(self):
            self.deps = FakeDeps()

    ctx = FakeCtx()
    result = tools.search_files(ctx, path=str(sample_tree), extension="py")
    assert "3 found" in result
    # The DataFrame should have been populated on the deps object.
    assert ctx.deps.current_df is not None
