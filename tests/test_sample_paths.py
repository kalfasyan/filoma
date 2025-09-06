from filoma.directories.directory_profiler import DirectoryProfiler


def test_sample_paths_fd_flags(monkeypatch, tmp_path):
    # Create a small filesystem tree for the python sample
    (tmp_path / "a.txt").write_text("1")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.txt").write_text("2")

    # Spy replacement for FdIntegration that records the kwargs it was called with
    class SpyFd:
        calls = []

        def __init__(self):
            pass

        def find(self, *args, **kwargs):
            # record the kwargs for assertions
            SpyFd.calls.append(kwargs)
            # return a predictable small list matching requested max_results
            maxr = kwargs.get("max_results") or 2
            file_types = kwargs.get("file_types")
            if file_types == ["d"]:
                return [str(tmp_path / "sub")][:maxr]
            return [str(tmp_path / "a.txt"), str(tmp_path / "sub" / "b.txt")][:maxr]

    # Ensure the directory_profiler will try to call our spy (force FD_AVAILABLE)
    monkeypatch.setattr("filoma.directories.directory_profiler.FD_AVAILABLE", True)
    monkeypatch.setattr("filoma.directories.directory_profiler.FdIntegration", SpyFd)

    profiler = DirectoryProfiler(search_backend="auto")
    samples = profiler.sample_paths(str(tmp_path), sample_size=2)

    # Basic shape
    assert set(samples.keys()) == {"fd_files", "fd_dirs", "python_files"}

    # fd spy should have been called at least twice (files and dirs)
    assert len(SpyFd.calls) >= 2

    # Find at least one call where the auto-mode flags were applied
    found = False
    for call in SpyFd.calls:
        if call.get("search_hidden") is True and call.get("no_ignore") is True and call.get("follow_links") is True:
            found = True
            break
    assert found, f"Expected fd.find to be called with search_hidden/no_ignore/follow_links; calls={SpyFd.calls}"


def test_sample_paths_python_sample_size(monkeypatch, tmp_path):
    # Create files in tmp_path
    files = [tmp_path / f"file{i}.txt" for i in range(5)]
    for f in files:
        f.write_text("x")

    # Prevent calling the real fd binary by disabling FD_AVAILABLE
    monkeypatch.setattr("filoma.directories.directory_profiler.FD_AVAILABLE", False)

    profiler = DirectoryProfiler()
    samples = profiler.sample_paths(str(tmp_path), sample_size=3)

    # Python sample should include up to the requested sample_size files
    assert isinstance(samples["python_files"], list)
    assert 0 < len(samples["python_files"]) <= 3
