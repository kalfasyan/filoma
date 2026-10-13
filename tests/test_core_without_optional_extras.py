"""Core workflows must keep working when only the base dependencies are installed.

The agent stack (pydantic-ai, mcp), the RAG stack (lancedb, sentence-transformers,
pyarrow) and pandas live in optional extras. These tests simulate a lean install
by running a fresh interpreter in which those packages are unimportable.
"""

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

_BLOCKED = (
    "pydantic_ai",
    "mcp",
    "dotenv",
    "openai",
    "lancedb",
    "sentence_transformers",
    "pandas",
    "pyarrow",
    "IPython",
)

_PRELUDE = f"""
import sys
for _name in {_BLOCKED!r}:
    sys.modules[_name] = None  # makes `import <name>` raise ImportError
"""


def _run(code: str, cwd: Path) -> subprocess.CompletedProcess:
    script = _PRELUDE + textwrap.dedent(code)
    return subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, cwd=cwd, timeout=180)


def _assert_ok(proc: subprocess.CompletedProcess) -> None:
    assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"


@pytest.fixture
def dataset(tmp_path):
    """Small dataset: one valid PNG, one duplicate pair, one text file."""
    from PIL import Image

    root = tmp_path / "data"
    root.mkdir()
    Image.new("RGB", (8, 8), (10, 120, 200)).save(root / "a.png")
    (root / "one.txt").write_text("hello world")
    (root / "two.txt").write_text("hello world")
    (tmp_path / "gates.yml").write_text("gates:\n  corrupted_files: 0\n  zero_byte_files: 0\n  duplicate_ratio_pct: 100\n")
    return root


def test_probe_and_dataframe_without_extras(dataset):
    """probe / probe_to_df / snapshot / Pipeline do not need any optional package."""
    proc = _run(
        f"""
        import filoma as flm

        analysis = flm.probe({str(dataset)!r})
        assert analysis.summary["total_files"] == 3
        df = flm.probe_to_df({str(dataset)!r})
        assert len(df) == 3
        snap = flm.snapshot({str(dataset)!r})
        assert flm.verify_snapshot.__name__
        flm.Pipeline({str(dataset)!r}).scan().enrich().verify()
        """,
        dataset.parent,
    )
    _assert_ok(proc)


def test_audit_cli_with_gates_without_extras(dataset):
    """`filoma audit --gates` (the CI entry point) works without pydantic-ai, pandas or lancedb."""
    gates = dataset.parent / "gates.yml"
    proc = _run(
        f"""
        from typer.testing import CliRunner
        from filoma.cli import app

        result = CliRunner().invoke(app, ["audit", {str(dataset)!r}, "--gates", {str(gates)!r}, "--export", {str(dataset.parent / "report.json")!r}, "--format", "json"])
        print(result.output)
        assert result.exit_code == 0, result.exit_code
        """,
        dataset.parent,
    )
    _assert_ok(proc)
    assert (dataset.parent / "report.json").exists()


def test_quality_scan_without_pandas(dataset):
    """DatasetVerifier (class-balance check included) must not require pandas."""
    (dataset / "labels.csv").write_text("filename,label\na.png,cat\nb.png,dog\nc.png,cat\n")
    proc = _run(
        f"""
        from filoma.core.verifier import DatasetVerifier

        result = DatasetVerifier({str(dataset)!r}).check_class_balance()
        assert result == {{"class_distribution": {{"cat": 2, "dog": 1}}}}, result
        """,
        dataset.parent,
    )
    _assert_ok(proc)


@pytest.mark.parametrize(
    "args",
    [["ask", "how many files?"], ["chat"], ["filaraki", "chat"], ["mcp", "serve"]],
)
def test_agent_commands_explain_missing_extra(dataset, args):
    """Agent-only CLI commands exit with an install hint instead of a traceback."""
    proc = _run(
        f"""
        from typer.testing import CliRunner
        from filoma.cli import app

        result = CliRunner().invoke(app, {args!r})
        assert result.exit_code == 1, (result.exit_code, result.output)
        assert "filoma[agent]" in result.output, result.output
        """,
        dataset.parent,
    )
    _assert_ok(proc)


def test_get_agent_raises_helpful_error(tmp_path):
    """The Python API gives the same hint."""
    proc = _run(
        """
        import filoma as flm

        try:
            flm.ask("hi")
        except ImportError as exc:
            assert "filoma[agent]" in str(exc), str(exc)
        else:
            raise SystemExit("expected ImportError")
        """,
        tmp_path,
    )
    _assert_ok(proc)
