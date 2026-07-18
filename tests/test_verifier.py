from pathlib import Path

import pytest

from filoma.core.verifier import DatasetVerifier


def test_check_integrity_includes_hidden_dirs_by_default(tmp_path: Path):
    """Default behavior (include_hidden=True) scans hidden directories too.

    Regression test: filoma's audit tools previously had no way to exclude
    hidden directories at all, so a user asking to "exclude hidden
    directories" would still get findings from e.g. .venv/.pixi.
    """
    (tmp_path / "visible").mkdir()
    (tmp_path / "visible" / "empty.txt").write_bytes(b"")
    hidden_dir = tmp_path / ".hidden"
    hidden_dir.mkdir()
    (hidden_dir / "empty.txt").write_bytes(b"")

    verifier = DatasetVerifier(str(tmp_path))
    results = verifier.check_integrity()
    found_paths = {f["path"] for f in results["failed_files"]}

    assert str(tmp_path / "visible" / "empty.txt") in found_paths
    assert str(hidden_dir / "empty.txt") in found_paths


def test_check_integrity_can_exclude_hidden_dirs(tmp_path: Path):
    """include_hidden=False prunes dot-directories from every check."""
    (tmp_path / "visible").mkdir()
    (tmp_path / "visible" / "empty.txt").write_bytes(b"")
    hidden_dir = tmp_path / ".hidden"
    hidden_dir.mkdir()
    (hidden_dir / "empty.txt").write_bytes(b"")

    verifier = DatasetVerifier(str(tmp_path), include_hidden=False)
    results = verifier.check_integrity()
    found_paths = {f["path"] for f in results["failed_files"]}

    assert str(tmp_path / "visible" / "empty.txt") in found_paths
    assert str(hidden_dir / "empty.txt") not in found_paths
    assert not any(".hidden" in p for p in found_paths)


@pytest.mark.skip(reason="Too slow, needs optimization")
def test_verifier_on_weeds_dataset():
    dataset_path = Path("notebooks/Weeds-3/")
    if not dataset_path.exists():
        pytest.skip("Weeds-3 dataset not found")

    verifier = DatasetVerifier(str(dataset_path))
    results = verifier.run_all()

    assert "integrity" in results
    assert "dimensions" in results
    assert "duplicates" in results
    assert "class_balance" in results
    assert "leakage" in results
    assert "pixel_stats" in results

    # Test directory-based inference
    verifier_folder = DatasetVerifier(str(dataset_path))
    results_folder = verifier_folder.run_all(label_source="folder")
    assert "class_balance" in results_folder

    # Test explicit label source
    results_csv = verifier.run_all(label_source="csv")
    assert "class_balance" in results_csv

    verifier.print_summary()
