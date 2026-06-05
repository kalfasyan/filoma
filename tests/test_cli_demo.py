"""Smoke test for the `filoma demo` CLI command."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from filoma.cli import app


def test_demo_command_runs_end_to_end():
    """`filoma demo` should run the full pipeline and produce an HTML report."""
    runner = CliRunner()
    report_path = Path(tempfile.gettempdir()) / "filoma_demo_audit.html"
    if report_path.exists():
        report_path.unlink()

    with patch("filoma.cli._can_open_browser", return_value=True), patch("webbrowser.open") as mock_open:
        result = runner.invoke(app, ["demo"])

    assert result.exit_code == 0, result.output
    assert report_path.exists(), f"Expected report at {report_path}"
    assert report_path.stat().st_size > 0
    assert mock_open.called, "Demo should attempt to open the report in a browser"
    opened_url = mock_open.call_args.args[0]
    assert opened_url.startswith("file://")
    assert str(report_path) in opened_url
