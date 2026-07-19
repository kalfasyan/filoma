"""Regression tests for duplicate-count accuracy in the hygiene/audit tools.

`generate_hygiene_report` used to truncate its "duplicates" evidence to a
5-group sample, and `audit_dataset` naively summed over that truncated
sample to compute `duplicate_files_total` / `estimated_space_waste_bytes` —
silently reporting e.g. "10 duplicate files (0.04%)" on a dataset that
actually had thousands, because only the first 5 groups' files were ever
counted. These tests build a dataset with more than 5 duplicate groups and
assert the reported totals reflect the *entire* dataset, not the sample.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest
from PIL import Image

from filoma.core.verifier import DatasetVerifier
from filoma.filaraki.agent import FilarakiDeps
from filoma.filaraki.tools import _extract_json_payload, audit_dataset, generate_hygiene_report
from filoma.mcp_server import SimpleRunContext

N_DUPLICATE_GROUPS = 8  # deliberately > the 5-group evidence sample size


@pytest.fixture
def many_duplicates_dir(tmp_path):
    """A dataset with more duplicate groups than the evidence sample can hold.

    Uses per-group random noise images (not flat colors) because dHash
    encodes gradients between neighboring pixels — a solid-color image has
    zero internal gradient anywhere, so every flat color hashes identically
    regardless of the actual color, which would collapse all "groups" into
    one. Random noise gives each group's images a genuinely distinct hash
    while two saves of the *same* array produce byte-identical (and thus
    hash-identical) JPEGs, since PIL's encoder is deterministic for a given
    input array and save parameters.
    """
    import numpy as np

    for i in range(N_DUPLICATE_GROUPS):
        rng = np.random.default_rng(seed=i)
        arr = rng.integers(0, 256, size=(32, 32, 3), dtype=np.uint8)
        img = Image.fromarray(arr, mode="RGB")
        img.save(tmp_path / f"orig_{i}.jpg")
        img.save(tmp_path / f"copy_{i}.jpg")

    rng = np.random.default_rng(seed=99999)
    arr = rng.integers(0, 256, size=(32, 32, 3), dtype=np.uint8)
    Image.fromarray(arr, mode="RGB").save(tmp_path / "unique.jpg")
    return tmp_path


def test_dataset_verifier_find_duplicates_returns_full_groups(many_duplicates_dir):
    verifier = DatasetVerifier(str(many_duplicates_dir))
    result = verifier.find_duplicates()

    assert result["duplicate_count"] == N_DUPLICATE_GROUPS
    assert result["duplicate_file_count"] == N_DUPLICATE_GROUPS * 2
    assert len(result["duplicates"]) == N_DUPLICATE_GROUPS
    assert all(len(g) == 2 for g in result["duplicates"])


def test_generate_hygiene_report_evidence_reflects_full_dataset(many_duplicates_dir):
    report_text = generate_hygiene_report(None, str(many_duplicates_dir))
    payload = _extract_json_payload(report_text)
    assert payload is not None

    dup_issue = next(i for i in payload["issues"] if i["id"] == "hygiene-duplicates")
    evidence = dup_issue["evidence"]

    assert evidence["duplicate_count"] == N_DUPLICATE_GROUPS
    assert evidence["duplicate_file_count"] == N_DUPLICATE_GROUPS * 2
    assert evidence["largest_duplicate_group_size"] == 2
    assert evidence["estimated_space_waste_bytes"] > 0
    # The raw group list is still sampled for display, not silently expanded.
    assert len(evidence["duplicates"]) == 5


@pytest.mark.asyncio
async def test_audit_dataset_reports_true_duplicate_total_not_sample_size(many_duplicates_dir):
    """audit_dataset's `duplicate_files_total` must count all groups, not just the first 5."""
    ctx = SimpleRunContext(deps=FilarakiDeps(working_dir=str(many_duplicates_dir)))

    result_text = audit_dataset(ctx, str(many_duplicates_dir), mode="verbose")
    payload = json.loads(result_text) if result_text.strip().startswith("{") else None
    if payload is None:
        # audit_dataset returns a human-readable executive summary followed by
        # the machine-readable JSON in "reports"/"summary" form via export;
        # fall back to parsing the printed summary numbers instead.
        assert f"Duplicate groups: {N_DUPLICATE_GROUPS}" in result_text
        assert f"Duplicate files total: {N_DUPLICATE_GROUPS * 2}" in result_text
    else:
        summary = payload["summary"]
        assert summary["duplicate_groups"] == N_DUPLICATE_GROUPS
        assert summary["duplicate_files_total"] == N_DUPLICATE_GROUPS * 2
