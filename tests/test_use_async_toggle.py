import pytest

from filoma.directories.directory_profiler import RUST_ASYNC_AVAILABLE, DirectoryProfiler


def test_default_async_off():
    p = DirectoryProfiler()
    info = p.get_implementation_info()
    # Default should not enable async scanner
    assert info.get("using_async", False) is False


def test_explicit_use_async_off():
    p = DirectoryProfiler(use_async=False)
    info = p.get_implementation_info()
    assert info.get("using_async", False) is False


def test_explicit_use_async_on_when_available():
    # Only meaningful if RUST_ASYNC_AVAILABLE is True in the environment.
    if not RUST_ASYNC_AVAILABLE:
        pytest.skip("RUST_ASYNC_AVAILABLE is False in this environment; skipping on-available test")

    p = DirectoryProfiler(use_async=True)
    info = p.get_implementation_info()
    assert info.get("using_async") is True


def test_explicit_use_async_on_when_unavailable(monkeypatch):
    # Simulate async being unavailable by monkeypatching the module-level constant
    import filoma.directories.directory_profiler as dp_mod

    monkeypatch.setattr(dp_mod, "RUST_ASYNC_AVAILABLE", False)

    # Recreate profiler to pick up patched value
    p = DirectoryProfiler(use_async=True)
    info = p.get_implementation_info()
    # Should not report using_async because native async isn't available
    assert info.get("using_async", False) is False
