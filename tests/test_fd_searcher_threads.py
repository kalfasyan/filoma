from filoma.directories.fd_finder import FdFinder


def test_find_files_passes_threads(monkeypatch):
    captured = {}

    def fake_run_command(cmd, **kwargs):
        # capture the command invocation
        captured["cmd"] = cmd

        class Res:
            stdout = ""
            returncode = 0

        return Res()

    # Ensure FdIntegration thinks fd is available
    monkeypatch.setattr("filoma.core.command_runner.CommandRunner.get_command_version", lambda cmd: "fd 8.0")
    monkeypatch.setattr("filoma.core.command_runner.CommandRunner.run_command", fake_run_command)

    searcher = FdFinder()
    # Call with threads=2 and assert CommandRunner got --threads 2
    searcher.find_files(pattern=".*", path=".", threads=2)

    assert "--threads" in captured["cmd"]
    assert "2" in captured["cmd"]
