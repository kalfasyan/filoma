"""Hashing utilities for dataset integrity.

Provides consistent hashing implementations for fast, deep, and full integrity checks
across snapshots, manifests, and file profiles.
"""

import hashlib
import os
from pathlib import Path

from loguru import logger


def compute_fast_hash(path: Path, size: int, mtime: float) -> str:
    """Compute fast metadata-based hash."""
    content = f"{path.name}:{size}:{mtime}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def compute_deep_hash(path: Path) -> str:
    """Compute deep partial content hash (first/last 4KB)."""
    hasher = hashlib.sha256()
    chunk_size = 4096

    try:
        with open(path, "rb") as f:
            first_chunk = f.read(chunk_size)
            hasher.update(first_chunk)
            file_size = path.stat().st_size
            if file_size > chunk_size * 2:
                f.seek(-chunk_size, os.SEEK_END)
                last_chunk = f.read(chunk_size)
                hasher.update(last_chunk)
        return hasher.hexdigest()[:32]
    except (IOError, OSError) as e:
        logger.warning(f"Could not compute deep hash for {path}: {e}")
        return ""


def compute_full_hash(path: Path) -> str:
    """Compute full SHA-256 hash."""
    hasher = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            while chunk := f.read(8192):
                hasher.update(chunk)
        return hasher.hexdigest()
    except (IOError, OSError) as e:
        logger.warning(f"Could not compute full hash for {path}: {e}")
        return ""
