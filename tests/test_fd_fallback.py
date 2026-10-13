"""Automatic backend selection must not fail when the fd binary is missing."""

import pytest

from filoma.directories import DirectoryProfiler, DirectoryProfilerConfig


class _MissingFd:
    """Stands in for FdIntegration on a machine without the fd binary."""

    def __init__(self):
        self.version = None

    def is_available(self):
        return False


@pytest.fixture
def fd_module_without_binary(monkeypatch):
    """Simulate: no Rust extension, the fd wrapper imports, but the fd binary is absent."""
    monkeypatch.setattr("filoma.directories.directory_profiler.RUST_AVAILABLE", False)
    monkeypatch.setattr("filoma.directories.directory_profiler.RUST_PARALLEL_AVAILABLE", False)
    monkeypatch.setattr("filoma.directories.directory_profiler.FD_AVAILABLE", True)
    monkeypatch.setattr("filoma.directories.directory_profiler.FdIntegration", _MissingFd)


def test_auto_probe_falls_back_to_python_without_fd_binary(fd_module_without_binary, tmp_path):
    (tmp_path / "a.txt").write_text("hello")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.txt").write_text("hi")

    analysis = DirectoryProfiler(DirectoryProfilerConfig(show_progress=False)).probe(str(tmp_path))

    assert analysis.summary["total_files"] == 2


def test_explicit_fd_request_still_fails_without_binary(fd_module_without_binary, tmp_path):
    profiler = DirectoryProfiler(DirectoryProfilerConfig(search_backend="fd", show_progress=False))

    with pytest.raises(RuntimeError, match="fd integration not available"):
        profiler.probe(str(tmp_path))
