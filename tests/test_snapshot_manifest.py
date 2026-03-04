"""Fast tests for snapshot and manifest functionality.

These tests use tiny temporary directories so they stay very fast while
exercising the public APIs exposed via the top-level `filoma` package.
"""

import json
import tempfile
from pathlib import Path

import pytest

import filoma as flm
from filoma.core.manifest import Manifest


@pytest.fixture
def tiny_dir() -> str:
    """Create a tiny directory tree for snapshot/manifest tests."""
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        (base / "a").mkdir()
        (base / "b").mkdir()

        (base / "a" / "one.txt").write_text("one")
        (base / "a" / "two.txt").write_text("two")
        (base / "b" / "three.bin").write_bytes(b"\x00\x01\x02\x03")

        yield str(base)


class TestSnapshotAPI:
    """Validate the high-level snapshot + verify_snapshot helpers."""

    def test_roundtrip_fast_mode(self, tiny_dir: str, tmp_path: Path):
        """Snapshot + verify of an unchanged tree should fully match."""
        snap_path = tmp_path / "snap_fast.json"

        snap = flm.snapshot(tiny_dir, mode="fast", export=str(snap_path))
        assert snap.entries
        assert snap_path.exists()

        results = flm.verify_snapshot(str(snap_path))
        assert sorted(results["missing"]) == []
        assert sorted(results["modified"]) == []
        assert sorted(results["added"]) == []
        assert set(results["matched"]) == {e.path for e in snap.entries}

    def test_verify_detects_modification(self, tiny_dir: str, tmp_path: Path):
        """Changes to a file after snapshot should be reported as modified."""
        snap_path = tmp_path / "snap_change.json"

        flm.snapshot(tiny_dir, mode="fast", export=str(snap_path))
        target = Path(tiny_dir) / "a" / "one.txt"
        target.write_text("one-modified")

        results = flm.verify_snapshot(str(snap_path))
        modified_paths = {m["path"] for m in results["modified"]}
        assert str(Path("a") / "one.txt") in modified_paths
        assert results["missing"] == []

    def test_verify_detects_added_and_missing(self, tiny_dir: str, tmp_path: Path):
        """New / removed files relative to the snapshot are tracked."""
        snap_path = tmp_path / "snap_added_missing.json"

        _ = flm.snapshot(tiny_dir, mode="fast", export=str(snap_path))

        removed = Path(tiny_dir) / "a" / "two.txt"
        removed.unlink()
        added = Path(tiny_dir) / "a" / "new.txt"
        added.write_text("new")

        results = flm.verify_snapshot(str(snap_path))
        assert str(Path("a") / "two.txt") in results["missing"]
        assert str(Path("a") / "new.txt") in results["added"]


class TestManifestAPI:
    """Fast tests for manifest generation and verification."""

    def test_manifest_generate_and_verify(self, tiny_dir: str, tmp_path: Path):
        """Generate a manifest from a DataFrame and verify against disk."""
        df = flm.probe_to_df(tiny_dir, enrich=True)
        manifest = Manifest()

        data = manifest.generate(df, compute_hashes=True)
        assert data["summary"]["total_files"] == len(df)
        assert data["files"]

        manifest_path = tmp_path / "manifest.json"
        manifest.save(data, manifest_path)
        assert manifest_path.exists()

        results = manifest.verify(manifest_path)
        assert not results["missing"]
        assert not results["size_mismatch"]
        assert not results["hash_mismatch"]

    def test_manifest_verify_detects_change(self, tiny_dir: str, tmp_path: Path):
        """File content change should be reported as a hash mismatch."""
        df = flm.probe_to_df(tiny_dir, enrich=True)
        manifest = Manifest()

        data = manifest.generate(df, compute_hashes=True)
        manifest_path = tmp_path / "manifest_change.json"
        manifest.save(data, manifest_path)

        changed = Path(tiny_dir) / "b" / "three.bin"
        changed.write_bytes(b"\x10\x11\x12\x13")

        results = manifest.verify(manifest_path)
        assert results["matched"]
        assert not results["missing"]
        assert not results["size_mismatch"]
        assert results["hash_mismatch"]

    def test_manifest_file_format_is_json(self, tiny_dir: str, tmp_path: Path):
        """Saved manifest should be valid JSON with expected keys."""
        df = flm.probe_to_df(tiny_dir, enrich=False)
        manifest = Manifest()

        data = manifest.generate(df, compute_hashes=False)
        manifest_path = tmp_path / "manifest_format.json"
        manifest.save(data, manifest_path)

        loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert {"version", "created_at", "lineage", "summary", "files"} <= set(loaded.keys())
