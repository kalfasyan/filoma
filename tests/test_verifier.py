from pathlib import Path

import pytest

from filoma.core.verifier import DatasetVerifier


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
