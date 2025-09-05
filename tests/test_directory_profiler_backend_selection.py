from filoma.directories import DirectoryProfiler


def test_auto_prefers_fd_when_enabled(monkeypatch):
    """When both Rust and fd are available and use_fd=True, auto should pick fd."""
    # Simulate both backends available
    monkeypatch.setattr("filoma.directories.directory_profiler.RUST_AVAILABLE", True)
    monkeypatch.setattr("filoma.directories.directory_profiler.RUST_PARALLEL_AVAILABLE", True)
    monkeypatch.setattr("filoma.directories.directory_profiler.FD_AVAILABLE", True)

    # Create profiler that leaves search_backend on 'auto' and enables fd
    profiler = DirectoryProfiler(use_rust=True, use_fd=True, search_backend="auto")
    backend = profiler._choose_backend()
    assert backend == "fd", f"Expected 'fd' but got '{backend}'"


def test_auto_falls_back_to_rust_when_fd_disabled(monkeypatch):
    """If fd is not enabled, auto should pick rust when available."""
    monkeypatch.setattr("filoma.directories.directory_profiler.RUST_AVAILABLE", True)
    monkeypatch.setattr("filoma.directories.directory_profiler.RUST_PARALLEL_AVAILABLE", True)
    monkeypatch.setattr("filoma.directories.directory_profiler.FD_AVAILABLE", True)

    profiler = DirectoryProfiler(use_rust=True, use_fd=False, search_backend="auto")
    backend = profiler._choose_backend()
    assert backend == "rust", f"Expected 'rust' but got '{backend}'"
