import pytest

from filoma.directories.directory_profiler import RUST_ASYNC_AVAILABLE, DirectoryProfiler, DirectoryProfilerConfig


def test_default_async_off():
    p = DirectoryProfiler(DirectoryProfilerConfig())
    info = p.get_implementation_info()
    # Default should not enable async scanner
    assert info.get("using_async", False) is False


def test_explicit_use_async_off():
    p = DirectoryProfiler(DirectoryProfilerConfig(use_async=False))
    info = p.get_implementation_info()
    assert info.get("using_async", False) is False


def test_explicit_use_async_on_when_available():
    # Only meaningful if RUST_ASYNC_AVAILABLE is True in the environment.
    if not RUST_ASYNC_AVAILABLE:
        pytest.skip("RUST_ASYNC_AVAILABLE is False in this environment; skipping on-available test")

    p = DirectoryProfiler(DirectoryProfilerConfig(use_rust=True, use_async=True))
    info = p.get_implementation_info()
    assert info.get("using_async") is True


def test_explicit_use_async_on_when_unavailable(monkeypatch):
    # Simulate async being unavailable by monkeypatching the module-level constant
    import filoma.directories.directory_profiler as dp_mod

    monkeypatch.setattr(dp_mod, "RUST_ASYNC_AVAILABLE", False)

    # Recreate profiler to pick up patched value. The profiler constructor may
    # raise a RuntimeError when async is requested but not available; treat that
    # as an expected outcome for environments where async is not compiled in.
    try:
        p = DirectoryProfiler(DirectoryProfilerConfig(use_rust=True, use_async=True))
    except RuntimeError as e:
        # If the runtime complains about async not being available, that's fine.
        assert "Async Rust prober requested but not available" in str(e) or "async" in str(e).lower()
        return

    info = p.get_implementation_info()
    # Should not report using_async because native async isn't available
    assert info.get("using_async", False) is False
