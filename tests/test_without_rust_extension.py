"""filoma must keep working when the compiled Rust extension is unavailable.

The advertised backend order is Rust -> fd -> Python. A fresh interpreter in which
``filoma.filoma_core`` cannot be imported stands in for platforms or installs where
the extension is missing (for example a from-source build without a Rust toolchain).
"""

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

_PRELUDE = """
import sys
sys.modules["filoma.filoma_core"] = None  # makes `import filoma.filoma_core` raise ImportError
"""


def _run(code: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-c", _PRELUDE + textwrap.dedent(code)], capture_output=True, text=True, cwd=cwd, timeout=180)


@pytest.fixture
def dataset(tmp_path):
    root = tmp_path / "data"
    (root / "a").mkdir(parents=True)
    (root / "a" / "x.txt").write_text("hello")
    (root / "y.txt").write_text("hi")
    return root


def test_default_probe_falls_back_when_extension_missing(dataset):
    """``use_parallel`` defaults to True; it used to raise 'Parallel Rust requested but not available'."""
    proc = _run(
        f"""
        import filoma as flm
        from filoma.directories import directory_profiler as dp

        assert not dp.RUST_AVAILABLE and not dp.RUST_PARALLEL_AVAILABLE

        summary = flm.probe({str(dataset)!r}, show_progress=False).summary
        assert (summary["total_files"], summary["total_folders"], summary["total_size_bytes"]) == (2, 2, 7), summary

        df = flm.probe_to_df({str(dataset)!r}, show_progress=False)
        assert len(df) == 3
        """,
        dataset.parent,
    )
    assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"


def test_explicit_rust_request_still_errors_clearly(dataset):
    """Explicitly asking for Rust without the extension remains an error, not a silent fallback."""
    proc = _run(
        """
        from filoma.directories import DirectoryProfiler, DirectoryProfilerConfig

        try:
            DirectoryProfiler(DirectoryProfilerConfig(use_rust=True))
        except RuntimeError as exc:
            assert "Rust implementation requested" in str(exc), exc
        else:
            raise SystemExit("expected RuntimeError")
        """,
        dataset.parent,
    )
    assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"


def test_audit_cli_works_without_extension(dataset):
    """The CI entry point (`filoma audit`) must not need the compiled extension."""
    proc = _run(
        f"""
        from typer.testing import CliRunner
        from filoma.cli import app

        result = CliRunner().invoke(app, ["audit", {str(dataset)!r}, "--export", {str(dataset.parent / "r.json")!r}, "--format", "json"])
        print(result.output)
        assert result.exit_code == 0, result.exit_code
        """,
        dataset.parent,
    )
    assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
