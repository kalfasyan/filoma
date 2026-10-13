"""Direct tests for the HTML audit report renderer (extracted from ``audit_dataset``)."""

import pytest

from filoma.filaraki.audit_report import render_html_report


def _report(**summary):
    return {
        "version": "1.1",
        "summary": {"total_files_checked": 10, "duplicate_groups": 0, "corrupted_files": 0, **summary},
        "dataset_profile": {"extension_counts": {".png": 7, ".txt": 3}, "split_counts": {"train": 6, "valid": 4}},
        "reconciliation": {"status": "ok"},
    }


def test_renders_a_complete_document():
    page = render_html_report(_report(hygiene_score=90, migration_readiness=40), "/data/set", "concise")
    assert page.startswith("<!doctype html>")
    assert page.rstrip().endswith("</html>")
    assert "/data/set" in page
    assert ".png" in page
    assert "train: <strong>6</strong>" in page


def test_target_and_extension_names_are_escaped():
    report = _report()
    report["dataset_profile"]["extension_counts"] = {".<b>x</b>": 1}
    page = render_html_report(report, '/data/<script>alert("x")</script>', "verbose")
    assert "<script>alert" not in page
    assert "&lt;script&gt;" in page
    assert ".<b>x</b>" not in page


@pytest.mark.parametrize(
    ("score", "color"),
    [(95, "#10b981"), (80, "#10b981"), (60, "#f59e0b"), (49, "#ef4444")],
)
def test_score_color_thresholds(score, color):
    """Gauges are green from 80, amber from 50, red below."""
    page = render_html_report(_report(hygiene_score=score, migration_readiness=score), "/d", "concise")
    assert color in page


def test_warns_when_stage_counts_disagree():
    report = _report()
    report["reconciliation"] = {"status": "warn"}
    page = render_html_report(report, "/d", "concise")
    assert "recon-warn" in page
    assert "File counts differ" in page


def test_empty_report_still_renders():
    page = render_html_report({}, "/d", "concise")
    assert "<html" in page and "</html>" in page
