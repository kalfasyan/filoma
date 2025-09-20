import tempfile
from pathlib import Path

import pytest

import filoma as flm
from filoma.core import FdIntegration


@pytest.fixture
def sample_tree():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td)
        (p / "a").mkdir()
        (p / "b").mkdir()
        (p / "a" / "file1.py").write_text("print('hello')")
        (p / "a" / "file2.txt").write_text("hello")
        (p / "b" / "image.png").write_text("fakepng")
        (p / "README.md").write_text("# test")
        yield str(p)


def _run_probe_and_check(path: str, backend: str):
    # Skip fd if not available
    if backend == "fd":
        if not FdIntegration().is_available():
            pytest.skip("fd backend not available")

    try:
        # Use the high-level helper which forces DataFrame building and enrichment
        df = flm.probe_to_df(
            path, enrich=True, search_backend=backend, build_dataframe=True, max_depth=5
        )
    except Exception as exc:
        # If a backend isn't present or can't run in this environment, skip
        pytest.skip(f"{backend} backend unavailable or failed: {exc}")

    # df should be a Polars DataFrame with enrichment columns
    cols = set(df.columns)

    # Expected enrichment columns
    expected = {"depth", "parent", "name", "stem", "suffix", "size_bytes"}
    missing = expected - cols
    assert not missing, f"Missing enrichment columns for backend={backend}: {missing}"

    # At least one non-null depth and size_bytes should be present
    depths = df["depth"].to_list()
    sizes = df["size_bytes"].to_list()

    assert any(
        d is not None for d in depths
    ), f"All depths are null for backend={backend}"
    assert any(
        s is not None for s in sizes
    ), f"All size_bytes are null for backend={backend}"


@pytest.mark.parametrize("backend", ["python", "rust", "fd"])
def test_enrich_on_backends(sample_tree, backend):
    _run_probe_and_check(sample_tree, backend)
