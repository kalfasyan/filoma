import tempfile
from pathlib import Path

import pytest

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

    # Test verify using the manifest file
    results = ds.verify(snapshot_path=manifest_path)
    assert len(results["matched"]) == 2

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
