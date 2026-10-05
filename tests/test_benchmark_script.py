"""Smoke tests for ``benchmarks/benchmark.py`` and the task runners that invoke it."""

import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
BENCHMARK = ROOT / "benchmarks" / "benchmark.py"


def _run(path: Path, *backends: str) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(BENCHMARK), "--path", str(path), "--use-existing", "-n", "1"]
    for backend in backends:
        cmd += ["--backend", backend]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120)


@pytest.fixture
def tiny_tree(tmp_path):
    root = tmp_path / "tree"
    for i in range(3):
        (root / f"d{i}").mkdir(parents=True)
        for j in range(4):
            (root / f"d{i}" / f"f{j}.txt").write_text("x")
    return root


@pytest.mark.skipif(not BENCHMARK.exists(), reason="benchmarks/ not available")
def test_benchmark_backends_agree_on_a_plain_tree(tiny_tree):
    backends = ["os.walk", "python"] + (["cli-find"] if shutil.which("find") else [])
    proc = _run(tiny_tree, *backends)
    assert proc.returncode == 0, proc.stderr
    assert "Results:" in proc.stdout
    assert "disagree" not in proc.stdout


@pytest.mark.skipif(not BENCHMARK.exists() or not shutil.which("find"), reason="needs benchmarks/ and find")
def test_benchmark_flags_backends_that_disagree_on_file_count(tiny_tree):
    """os.walk counts a symlink to a file as a file; ``find -type f`` does not."""
    try:
        (tiny_tree / "link.txt").symlink_to(tiny_tree / "d0" / "f0.txt")
    except OSError:
        pytest.skip("symlinks not supported on this platform")
    proc = _run(tiny_tree, "os.walk", "cli-find")
    assert proc.returncode == 0, proc.stderr
    assert "disagree on the file count" in proc.stdout


@pytest.mark.skipif(not (ROOT / "scripts").is_dir(), reason="repository scripts/ not available (sdist or partial checkout)")
def test_poe_tasks_point_at_existing_scripts():
    """`poe benchmark` once pointed at scripts/benchmark.py, which did not exist."""
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    missing = []
    for name, task in config.get("tool", {}).get("poe", {}).get("tasks", {}).items():
        command = task if isinstance(task, str) else task.get("cmd", "")
        match = re.match(r"python\s+(\S+\.py)\b", command)
        if match and not (ROOT / match.group(1)).exists():
            missing.append(f"{name}: {match.group(1)}")
    assert not missing, f"poe tasks reference missing scripts: {missing}"
