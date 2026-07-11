import json
from pathlib import Path

from typer.testing import CliRunner

from filoma.cli._app import app

runner = CliRunner()


def test_watch_help():
    result = runner.invoke(app, ["watch", "--help"])
    assert result.exit_code == 0
    assert "watch" in result.stdout.lower()


def test_watch_missing_directory():
    result = runner.invoke(app, ["watch", "/nonexistent/path/12345"])
    assert result.exit_code == 1
    assert "does not exist" in result.stdout or "Error" in result.stdout


def test_watch_happy_path(tmp_path):
    tmp_path = Path(tmp_path)
    (tmp_path / "file1.txt").write_text("hello")
    (tmp_path / "file2.txt").write_text("world")

    result = runner.invoke(app, ["watch", str(tmp_path)])
    assert result.exit_code == 0
    assert "Matched" in result.stdout


def test_watch_with_export(tmp_path):
    tmp_path = Path(tmp_path)
    (tmp_path / "file1.txt").write_text("hello")

    export_file = tmp_path / "report.json"
    result = runner.invoke(app, ["watch", "--export", str(export_file), str(tmp_path)])
    assert result.exit_code == 0
    assert export_file.exists()
    report = json.loads(export_file.read_text())
    assert "matched" in report
    assert "modified" in report
    assert "missing" in report
    assert "added" in report


def test_watch_detects_new_file(tmp_path):
    tmp_path = Path(tmp_path)
    (tmp_path / "file1.txt").write_text("hello")

    snapshot_file = tmp_path / "snap.json"
    result = runner.invoke(
        app,
        ["watch", str(tmp_path), "--snapshot", str(snapshot_file)],
    )
    assert result.exit_code == 0

    (tmp_path / "file2.txt").write_text("new file")

    result = runner.invoke(
        app,
        ["watch", str(tmp_path), "--snapshot", str(snapshot_file)],
    )
    assert result.exit_code == 0
    assert "Added" in result.stdout


def test_watch_detects_modified_file(tmp_path):
    tmp_path = Path(tmp_path)
    (tmp_path / "file1.txt").write_text("hello")

    snapshot_file = tmp_path / "snap.json"
    result = runner.invoke(
        app,
        ["watch", str(tmp_path), "--snapshot", str(snapshot_file)],
    )
    assert result.exit_code == 0

    (tmp_path / "file1.txt").write_text("modified content here")

    result = runner.invoke(
        app,
        ["watch", str(tmp_path), "--snapshot", str(snapshot_file)],
    )
    assert result.exit_code == 0
    assert "Modified" in result.stdout


def test_watch_detects_missing_file(tmp_path):
    tmp_path = Path(tmp_path)
    (tmp_path / "file1.txt").write_text("hello")
    (tmp_path / "file2.txt").write_text("world")

    snapshot_file = tmp_path / "snap.json"
    result = runner.invoke(
        app,
        ["watch", str(tmp_path), "--snapshot", str(snapshot_file)],
    )
    assert result.exit_code == 0

    (tmp_path / "file1.txt").unlink()

    result = runner.invoke(
        app,
        ["watch", str(tmp_path), "--snapshot", str(snapshot_file)],
    )
    assert result.exit_code == 0
    assert "Missing" in result.stdout


def test_watch_invalid_mode(tmp_path):
    result = runner.invoke(app, ["watch", str(tmp_path), "--mode", "invalid"])
    assert result.exit_code == 1


def test_watch_gates_file_missing(tmp_path):
    result = runner.invoke(app, ["watch", str(tmp_path), "--gates", "/nonexistent/gates.yml"])
    assert result.exit_code == 1
