from filoma.files import FileProfiler


def test_file_profiler_basic(tmp_path):
    # Create a temporary file
    file_path = tmp_path / "testfile.txt"
    file_path.write_text("hello world")
    profiler = FileProfiler()
    filo = profiler.probe(str(file_path))
    report = filo.to_dict()
    assert report["path"] == str(file_path)
    assert report["size"] == 11
    assert report["is_file"] is True
    assert report["is_dir"] is False
    assert report["is_symlink"] is False
    assert report["owner"]
    assert report["group"]
    assert report["created"]
    assert report["modified"]
    assert report["accessed"]


def test_file_profiler_symlink(tmp_path):
    file_path = tmp_path / "target.txt"
    file_path.write_text("target")
    symlink_path = tmp_path / "link.txt"
    symlink_path.symlink_to(file_path)
    profiler = FileProfiler()
    filo = profiler.probe(str(symlink_path))
    report = filo.to_dict()
    assert report["is_symlink"] is True
    assert report["target_is_file"] is True  # symlink points to file
    assert report["target_is_dir"] is False
