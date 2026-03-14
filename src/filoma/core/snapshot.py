"""Dataset snapshot functionality for filoma.

Provides fast, multi-level integrity checking for dataset snapshots:
- Fast: Metadata-based hashing (size + mtime + filename)
- Deep: Partial content hashing (first/last 4KB)
- Full: Complete SHA-256 hashing
"""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union

from loguru import logger

from .hashes import compute_deep_hash, compute_fast_hash, compute_full_hash


@dataclass
class SnapshotEntry:
    """A single file entry in a dataset snapshot."""

    path: str
    size: int
    mtime: float
    mode: str = "fast"  # "fast", "deep", or "full"
    hash_fast: Optional[str] = None
    hash_deep: Optional[str] = None
    hash_full: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "path": self.path,
            "size": self.size,
            "mtime": self.mtime,
            "mode": self.mode,
            "hash_fast": self.hash_fast,
            "hash_deep": self.hash_deep,
            "hash_full": self.hash_full,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SnapshotEntry":
        """Create from dictionary."""
        return cls(
            path=data["path"],
            size=data["size"],
            mtime=data["mtime"],
            mode=data.get("mode", "fast"),
            hash_fast=data.get("hash_fast"),
            hash_deep=data.get("hash_deep"),
            hash_full=data.get("hash_full"),
        )


@dataclass
class DatasetSnapshot:
    """A complete snapshot of a dataset with integrity information."""

    root_path: str
    created_at: str
    mode: str  # "fast", "deep", or "full"
    entries: List[SnapshotEntry] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "version": "1.0",
            "root_path": self.root_path,
            "created_at": self.created_at,
            "mode": self.mode,
            "file_count": len(self.entries),
            "total_size": sum(e.size for e in self.entries),
            "entries": [e.to_dict() for e in self.entries],
            "metadata": self.metadata,
        }

    def save(self, path: Union[str, Path]) -> None:
        """Save snapshot to a JSON file."""
        path = Path(path)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
        logger.info(f"Snapshot saved to {path}")

    @classmethod
    def load(cls, path: Union[str, Path]) -> "DatasetSnapshot":
        """Load a snapshot from a JSON file."""
        path = Path(path)
        with open(path) as f:
            data = json.load(f)

        snapshot = cls(
            root_path=data["root_path"],
            created_at=data["created_at"],
            mode=data["mode"],
            metadata=data.get("metadata", {}),
        )
        snapshot.entries = [SnapshotEntry.from_dict(e) for e in data["entries"]]
        return snapshot


def _scan_directory(
    root_path: Path,
    mode: Literal["fast", "deep", "full"],
    include_hidden: bool = False,
    pattern: Optional[str] = None,
) -> List[SnapshotEntry]:
    """Scan directory and create snapshot entries."""
    entries = []

    for dirpath, dirnames, filenames in os.walk(root_path):
        # Filter hidden directories if needed
        if not include_hidden:
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]

        for filename in filenames:
            # Skip hidden files
            if not include_hidden and filename.startswith("."):
                continue

            file_path = Path(dirpath) / filename
            rel_path = file_path.relative_to(root_path)

            # Apply pattern filter if specified
            if pattern and not rel_path.match(pattern):
                continue

            try:
                stat = file_path.stat()
                entry = SnapshotEntry(
                    path=str(rel_path),
                    size=stat.st_size,
                    mtime=stat.st_mtime,
                    mode=mode,
                )

                # Compute hash based on mode
                if mode == "fast":
                    entry.hash_fast = compute_fast_hash(file_path, entry.size, entry.mtime)
                elif mode == "deep":
                    entry.hash_fast = compute_fast_hash(file_path, entry.size, entry.mtime)
                    entry.hash_deep = compute_deep_hash(file_path)
                elif mode == "full":
                    entry.hash_fast = compute_fast_hash(file_path, entry.size, entry.mtime)
                    entry.hash_deep = compute_deep_hash(file_path)
                    entry.hash_full = compute_full_hash(file_path)

                entries.append(entry)

            except (OSError, IOError) as e:
                logger.warning(f"Could not process {file_path}: {e}")
                continue

    return entries


def snapshot(
    path: Union[str, Path],
    mode: Literal["fast", "deep", "full"] = "fast",
    export: Optional[Union[str, Path]] = None,
    include_hidden: bool = False,
    pattern: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> DatasetSnapshot:
    """Create a snapshot of a dataset with configurable integrity checking.

    Three integrity levels:
    - "fast": Hash of filename + size + mtime (99% effective for accidental changes)
    - "deep": Fast + hash of first/last 4KB (detects header/corruption changes)
    - "full": Complete SHA-256 hash (audit mode, slow for large files)

    Args:
        path: Path to the dataset directory to snapshot
        mode: Integrity level - "fast", "deep", or "full"
        export: Optional path to save the snapshot JSON file
        include_hidden: Whether to include hidden files/directories
        pattern: Optional glob pattern to filter files (e.g., "*.txt")
        metadata: Optional metadata dictionary to include in snapshot

    Returns:
        DatasetSnapshot object containing all file entries and hashes

    Example:
        >>> import filoma as flm
        >>> snap = flm.snapshot("./my_dataset", mode="fast")
        >>> print(f"Found {len(snap.entries)} files")
        >>>
        >>> # Save for later verification
        >>> flm.snapshot("./my_dataset", mode="deep", export="manifest.json")

    """
    root_path = Path(path).resolve()
    if not root_path.exists():
        raise FileNotFoundError(f"Path does not exist: {root_path}")
    if not root_path.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {root_path}")

    logger.info(f"Creating {mode} snapshot of {root_path}")

    # Scan directory and compute hashes
    entries = _scan_directory(root_path, mode, include_hidden, pattern)

    # Create snapshot
    snapshot = DatasetSnapshot(
        root_path=str(root_path),
        created_at=datetime.now().isoformat(),
        mode=mode,
        entries=entries,
        metadata=metadata or {},
    )

    # Save if export path provided
    if export:
        snapshot.save(export)

    logger.success(f"Snapshot complete: {len(entries)} files, {sum(e.size for e in entries):,} bytes total")

    return snapshot


def verify(
    snapshot_path: Union[str, Path],
    target_path: Optional[Union[str, Path]] = None,
    mode: Optional[Literal["fast", "deep", "full"]] = None,
) -> Dict[str, Any]:
    """Verify a directory against a saved snapshot.

    Args:
        snapshot_path: Path to the saved snapshot JSON file
        target_path: Optional path to verify (defaults to snapshot's root_path)
        mode: Verification mode (defaults to snapshot's mode)

    Returns:
        Dictionary with verification results:
        - "matched": List of files that match
        - "modified": List of files that changed
        - "missing": List of files in snapshot but not in directory
        - "added": List of files in directory but not in snapshot

    """
    # Load snapshot
    snap = DatasetSnapshot.load(snapshot_path)

    # Determine target path
    if target_path is None:
        target_path = Path(snap.root_path)
    else:
        target_path = Path(target_path)

    # Determine verification mode
    verify_mode = mode or snap.mode

    logger.info(f"Verifying {target_path} against snapshot (mode: {verify_mode})")

    # Create current snapshot for comparison
    from typing import cast

    current = snapshot(target_path, mode=cast(Literal["fast", "deep", "full"], verify_mode))

    # Build lookup dictionaries
    snap_files = {e.path: e for e in snap.entries}
    current_files = {e.path: e for e in current.entries}

    results = {
        "matched": [],
        "modified": [],
        "missing": [],
        "added": [],
    }

    # Check for matches and modifications
    for path, snap_entry in snap_files.items():
        if path not in current_files:
            results["missing"].append(path)
            continue

        current_entry = current_files[path]

        # Compare based on verification mode
        match = False
        if verify_mode == "fast":
            match = snap_entry.hash_fast == current_entry.hash_fast
        elif verify_mode == "deep":
            match = snap_entry.hash_fast == current_entry.hash_fast and snap_entry.hash_deep == current_entry.hash_deep
        elif verify_mode == "full":
            match = snap_entry.hash_full == current_entry.hash_full

        if match:
            results["matched"].append(path)
        else:
            results["modified"].append(
                {
                    "path": path,
                    "old_size": snap_entry.size,
                    "new_size": current_entry.size,
                    "old_mtime": snap_entry.mtime,
                    "new_mtime": current_entry.mtime,
                }
            )

    # Check for added files
    for path in current_files:
        if path not in snap_files:
            results["added"].append(path)

    # Summary
    total = len(snap_files)
    matched = len(results["matched"])
    modified = len(results["modified"])
    missing = len(results["missing"])
    added = len(results["added"])

    logger.info(f"Verification complete: {matched}/{total} matched, {modified} modified, {missing} missing, {added} added")

    return results
