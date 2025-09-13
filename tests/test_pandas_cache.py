import pytest

from filoma.dataframe import DataFrame


def test_invalidate_on_setitem(tmp_path):
    paths = ["/tmp/a.py", "/tmp/b.py"]
    df = DataFrame(paths)

    # Ensure pandas is available; skip if not
    try:
        _ = df.pandas_cached
    except ImportError:
        pytest.skip("pandas not installed")

    # Create a cached pandas view
    cached = df.pandas_cached
    assert cached is not None

    # Mutate via assignment and ensure cache invalidated
    df["newcol"] = [1, 2]
    assert df._pd_cache is None


def test_invalidate_on_delegated_call(monkeypatch):
    paths = ["/tmp/a.py", "/tmp/b.py"]
    df = DataFrame(paths)

    try:
        _ = df.pandas_cached
    except ImportError:
        pytest.skip("pandas not installed")

    # Create a cached pandas view
    _ = df.pandas_cached
    assert df._pd_cache is not None

    # Monkeypatch an underlying Polars method to simulate an in-place mutator
    def fake_mutator(*args, **kwargs):
        # Simulate an in-place operation by returning None
        return None

    # Some Polars DataFrame implementations are C-backed and don't accept
    # setattr on the instance. Wrap the underlying `_df` in a small helper
    # object that delegates attribute access to the original Polars object
    # but exposes `fake_mutator` so the wrapper's __getattr__ finds it.
    orig = df._df

    class DelegatingDF:
        def __init__(self, orig):
            self._orig = orig

        def __getattr__(self, name):
            return getattr(self._orig, name)

        def fake_mutator(self, *args, **kwargs):
            return None

    monkeypatch.setattr(df, "_df", DelegatingDF(orig), raising=True)

    # Access via wrapper delegated call; should call our fake_mutator and
    # cause the wrapper to invalidate the pandas cache
    getattr(df, "fake_mutator")()
    assert df._pd_cache is None
