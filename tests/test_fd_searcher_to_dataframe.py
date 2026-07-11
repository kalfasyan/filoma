from filoma.directories.fd_finder import FdFinder


def test_to_dataframe_returns_dataframe_or_list(monkeypatch):
    fake_paths = ["/tmp/a.py", "/tmp/b.py"]

    def fake_search(self, *args, **kwargs):
        return fake_paths

    # Pretend fd is available so FdFinder routes through FdIntegration.find
    # rather than its pure-Python fallback.
    monkeypatch.setattr("filoma.core.fd_integration.FdIntegration.is_available", lambda self: True)
    monkeypatch.setattr("filoma.core.fd_integration.FdIntegration.find", fake_search)

    s = FdFinder()
    s.fd.available = True  # in case __init__ already cached availability
    df_or_list = s.to_dataframe(r".*\\.py$", path=".")

    # If DataFrame available, expect object with .df attribute; otherwise list
    if hasattr(df_or_list, "df"):
        assert list(df_or_list.df["path"].to_list()) == fake_paths
    else:
        assert df_or_list == fake_paths
