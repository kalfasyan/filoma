import tempfile
from pathlib import Path

import pytest

import filoma
from filoma import Dataset
from filoma.filaraki import get_agent
from filoma.filaraki.agent import FilarakiAgent


@pytest.fixture
def temp_dataset():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "subdir").mkdir()
        (root / "file1.txt").write_text("hello")
        (root / "subdir/file2.txt").write_text("world")
        yield str(root)  # Return as string to match existing FileProfiler/DirectoryProfiler expectations


def test_dataset_basic_operations(temp_dataset):
    ds = Dataset(temp_dataset)

    # Create temp manifest file
    manifest_path = Path(temp_dataset) / "manifest.json"

    # Test snapshot and export
    ds.snap(mode="fast", export=manifest_path)
    assert ds.snapshot is not None
    assert len(ds.snapshot.entries) == 2

    # Test verify using the manifest file (now returns self; result via .verification)
    ds.verify(snapshot_path=manifest_path)
    assert ds.verification is not None
    assert len(ds.verification["matched"]) == 2

    # Test dataframe
    df = ds.to_dataframe()
    assert df.df.height >= 2


def test_dataset_invalid_path():
    with pytest.raises(FileNotFoundError):
        Dataset("/non/existent/path")


def test_dataset_get_filaraki(temp_dataset):
    ds = Dataset(temp_dataset)

    agent = ds.get_filaraki()
    assert isinstance(agent, FilarakiAgent)
    # Check resolved paths to handle macOS symlink (/var/folders -> /private/var/folders)
    assert Path(agent.default_working_dir).resolve() == Path(temp_dataset).resolve()


def test_get_agent_working_dir(temp_dataset):
    agent = get_agent(working_dir=temp_dataset)
    assert isinstance(agent, FilarakiAgent)
    # Check resolved paths to handle macOS symlink (/var/folders -> /private/var/folders)
    assert Path(agent.default_working_dir).resolve() == Path(temp_dataset).resolve()


def test_dataset_fluent_chain(temp_dataset):
    """End-to-end fluent chain: scan().enrich().verify().report()."""
    ds = Dataset(temp_dataset).scan().enrich().verify().report()

    # Each stage populates its cache and returns the same Dataset.
    assert isinstance(ds, Dataset)
    assert ds.snapshot is not None
    assert ds.dataframe is not None
    assert ds.dataframe.df.height >= 2
    assert ds.verification is not None
    assert "matched" in ds.verification
    assert ds.report_path is not None
    assert ds.report_path.exists()
    assert ds.report_path.stat().st_size > 0


def test_verify_auto_snapshots_when_chain_starts_with_verify(temp_dataset):
    """``ds.verify()`` without a prior ``scan()`` snapshots in-memory and verifies."""
    ds = Dataset(temp_dataset).verify()
    assert ds.snapshot is not None
    assert ds.verification is not None
    assert len(ds.verification["matched"]) == 2


def test_pipeline_is_dataset_alias():
    """``flm.Pipeline`` and ``flm.Dataset`` are the same class."""
    assert filoma.Pipeline is filoma.Dataset


def test_invalidate_cache_clears_fluent_results(temp_dataset):
    ds = Dataset(temp_dataset).scan().enrich().verify()
    assert ds.dataframe is not None
    assert ds.verification is not None

    ds.invalidate_cache()
    assert ds.dataframe is None
    assert ds.verification is None
    assert ds.quality is None
    assert ds.duplicates is None
    assert ds.report_path is None
