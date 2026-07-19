"""Tests for the `filoma dedup` CLI command.

Regression coverage for two bugs found together:

1. `filoma dedup <single-directory>` crashed unconditionally with
   "data must be a Polars DataFrame, dict of columns, list of paths, or
   None" — the vstack-combine loop only unwraps the `filoma.DataFrame`
   returned by `probe_to_df()` into a raw Polars DataFrame when there are
   2+ paths; with exactly one path (the common case) the loop never runs,
   so the still-wrapped `filoma.DataFrame` got passed straight back into
   `filoma.DataFrame(...)`, which doesn't accept another wrapper instance.
2. `filoma dedup` always ran the O(n^2) text/image near-duplicate passes
   (mode="auto") with no way to opt out, which can make it hang/take a
   very long time on a dataset with many images/text files. Added
   `--mode` to allow a fast exact-only pass.
"""

from __future__ import annotations

from typer.testing import CliRunner

from filoma.cli import app


def test_dedup_single_directory_does_not_crash(tmp_path):
    """Regression test: a single path used to crash with a DataFrame-construction error."""
    (tmp_path / "a.txt").write_text("same content")
    (tmp_path / "b.txt").write_text("same content")

    runner = CliRunner()
    result = runner.invoke(app, ["dedup", str(tmp_path), "--mode", "exact"])

    assert result.exit_code == 0, result.output
    assert "must be a Polars DataFrame" not in result.output
    assert "Error during duplicate check" not in result.output
    assert "Exact duplicates" in result.output


def test_dedup_multiple_directories_still_works(tmp_path):
    """The multi-path case (which happened to work before) must keep working."""
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()
    (dir_a / "x.txt").write_text("shared content")
    (dir_b / "x.txt").write_text("shared content")

    runner = CliRunner()
    result = runner.invoke(app, ["dedup", str(dir_a), str(dir_b), "--mode", "exact"])

    assert result.exit_code == 0, result.output
    assert "Exact duplicates" in result.output


def test_dedup_mode_exact_skips_text_and_image_categories(tmp_path):
    """--mode exact must report 0 text/image groups (not compute them at all)."""
    (tmp_path / "a.txt").write_text("the quick brown fox jumps over the lazy dog")
    (tmp_path / "b.txt").write_text("the quick brown fox jumped over the lazy dog")

    runner = CliRunner()
    result = runner.invoke(app, ["dedup", str(tmp_path), "--mode", "exact"])

    assert result.exit_code == 0, result.output
    assert "No text duplicates found." in result.output
    assert "No image duplicates found." in result.output


def test_dedup_rejects_unknown_mode(tmp_path):
    runner = CliRunner()
    result = runner.invoke(app, ["dedup", str(tmp_path), "--mode", "bogus"])

    assert result.exit_code != 0
    assert "mode must be one of" in result.output
