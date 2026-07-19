"""Duplicate detection and similarity helpers for files.

This module provides:
- exact file hashing (`compute_sha256`)
- text shingles + Jaccard similarity (`text_shingles`, `jaccard_similarity`)
- optional MinHash if `datasketch` is installed (`minhash_signature`)
- image perceptual hashes: aHash and dHash (`ahash_image`, `dhash_image`) using Pillow when available
- high-level `find_duplicates` that can detect exact, near-duplicate text and image files
- `summarize_duplicate_directories` to roll file-level duplicate groups up into
  directory-pair overlap stats, for spotting near-duplicate/mirrored folder
  trees without reading a report listing every individual duplicate file

The implementation avoids hard dependencies; Pillow and datasketch are optional.
"""

from __future__ import annotations

import hashlib
import os
import re
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

try:
    from PIL import Image
except Exception:  # pragma: no cover - PIL optional
    Image = None

try:
    from datasketch import MinHash
except Exception:  # pragma: no cover - datasketch optional
    MinHash = None


def compute_sha256(path: str, block_size: int = 65536) -> str:
    """Compute the SHA256 hex digest for a file at `path`."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(block_size), b""):
            h.update(block)
    return h.hexdigest()


def file_fingerprint(path: str) -> Dict[str, object]:
    """Return a small fingerprint dict for `path` (size, mtime, sha256)."""
    st = os.stat(path)
    return {
        "path": path,
        "size": st.st_size,
        "mtime": st.st_mtime,
        "sha256": compute_sha256(path),
    }


def _normalize_tokens(text: str) -> List[str]:
    # lowercase + keep alphanumerics as tokens
    tokens = re.findall(r"\w+", text.lower())

    # very small stemmer: strip common verb/plural endings when long enough
    def stem(t: str) -> str:
        if len(t) > 4:
            return re.sub(r"(ed|ing|s)$", "", t)
        if len(t) > 3:
            return re.sub(r"(s)$", "", t)
        return t

    return [stem(t) for t in tokens]


def text_shingles(text: str, k: int = 3) -> Set[str]:
    """Return k-shingles (space-joined tokens) for `text`."""
    tokens = _normalize_tokens(text)
    if len(tokens) < k:
        return set([" ".join(tokens)])
    return set(" ".join(tokens[i : i + k]) for i in range(len(tokens) - k + 1))


def jaccard_similarity(a: Set[str], b: Set[str]) -> float:
    """Compute Jaccard similarity between two shingle sets."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = a.intersection(b)
    uni = a.union(b)
    return len(inter) / len(uni)


def minhash_signature(text: str, num_perm: int = 128, k: int = 3):
    """Return a MinHash object for `text` if datasketch is available, else a naive hashed signature list.

    The naive fallback is deterministic but not streaming-friendly or space-efficient.
    """
    shingles = text_shingles(text, k=k)
    if MinHash is not None:
        m = MinHash(num_perm=num_perm)
        for sh in shingles:
            m.update(sh.encode("utf8"))
        return m
    # fallback: return sorted list of small hashes (not true MinHash, but useful for cheap grouping)
    sig = sorted(int(hashlib.sha1(s.encode("utf8"), usedforsecurity=False).hexdigest()[:8], 16) for s in shingles)
    return sig


def _int_to_hex(i: int, width: int = 16) -> str:
    return f"{i:0{width}x}"


def _hamming_int(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def ahash_image(path: str, hash_size: int = 8) -> str:
    """Compute average-hash (aHash) for an image file at `path`."""
    if Image is None:
        raise RuntimeError("Pillow is required for image hashing (install pillow)")
    img = Image.open(path).convert("L").resize((hash_size, hash_size), Image.Resampling.LANCZOS)
    pixels = list(img.getdata())
    avg = sum(pixels) / len(pixels)
    bits = 0
    for p in pixels:
        bits = (bits << 1) | (1 if p >= avg else 0)
    return _int_to_hex(bits, width=hash_size * hash_size // 4)


def dhash_image(path: str, hash_size: int = 8) -> str:
    """Compute difference-hash (dHash) for an image file at `path`."""
    if Image is None:
        raise RuntimeError("Pillow is required for image hashing (install pillow)")
    img = Image.open(path).convert("L").resize((hash_size + 1, hash_size), Image.Resampling.LANCZOS)
    pixels = list(img.getdata())
    bits = 0
    for row in range(hash_size):
        for col in range(hash_size):
            left = pixels[row * (hash_size + 1) + col]
            right = pixels[row * (hash_size + 1) + col + 1]
            bits = (bits << 1) | (1 if left > right else 0)
    return _int_to_hex(bits, width=hash_size * hash_size // 4)


def hamming_distance_hex(a_hex: str, b_hex: str) -> int:
    """Return Hamming distance between two hex-encoded hashes."""
    a = int(a_hex, 16)
    b = int(b_hex, 16)
    return _hamming_int(a, b)


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tif", ".tiff", ".webp"}


def is_image_path(path: str) -> bool:
    """Return True if `path` has a known image file extension."""
    return os.path.splitext(path)[1].lower() in IMAGE_EXTS


def find_duplicates(
    paths: Iterable[str],
    mode: str = "auto",
    text_k: int = 3,
    text_threshold: float = 0.8,
    image_hash: str = "ahash",
    image_max_distance: int = 5,
) -> Dict[str, List[List[str]]]:
    """Find duplicate groups among `paths` and return them by type.

    Returns a dict with keys ``exact``, ``text``, and ``image`` each mapping
    to lists of duplicate groups found.

    Parameters
    ----------
    paths : Iterable[str]
        Iterable of filesystem paths to inspect.
    mode : str
        Search mode: 'auto', 'exact', 'text', 'image', or 'mixed'.
    text_k : int
        Shingle size used for text similarity.
    text_threshold : float
        Jaccard similarity threshold for grouping text duplicates.
    image_hash : str
        Which image hash to use: 'ahash' or 'dhash'.
    image_max_distance : int
        Maximum Hamming distance to consider images duplicates.

    """
    paths = list(paths)
    exact_groups = defaultdict(list)
    for p in paths:
        try:
            h = compute_sha256(p)
        except Exception:
            h = None
        exact_groups[h].append(p)

    exact = [g for g in exact_groups.values() if len(g) > 1]

    text_groups: List[List[str]] = []
    image_groups: List[List[str]] = []

    # Prepare lists
    text_candidates = [p for p in paths if not is_image_path(p)]
    image_candidates = [p for p in paths if is_image_path(p)]

    # Text similarity (shingle + Jaccard)
    shingles_map = {}
    for p in text_candidates:
        try:
            with open(p, "r", encoding="utf8") as f:
                txt = f.read()
        except Exception:
            continue
        shingles_map[p] = text_shingles(txt, k=text_k)

    visited = set()
    for a in list(shingles_map):
        if a in visited:
            continue
        group = [a]
        visited.add(a)
        for b in list(shingles_map):
            if b in visited or a == b:
                continue
            sim = jaccard_similarity(shingles_map[a], shingles_map[b])
            if sim >= text_threshold:
                group.append(b)
                visited.add(b)
        if len(group) > 1:
            text_groups.append(group)

    # Image similarity using perceptual hashes
    image_hashes = {}
    for p in image_candidates:
        try:
            if image_hash == "dhash":
                h = dhash_image(p)
            else:
                h = ahash_image(p)
            image_hashes[p] = h
        except Exception:
            continue

    visited = set()
    for a in list(image_hashes):
        if a in visited:
            continue
        group = [a]
        visited.add(a)
        for b in list(image_hashes):
            if b in visited or a == b:
                continue
            dist = hamming_distance_hex(image_hashes[a], image_hashes[b])
            if dist <= image_max_distance:
                group.append(b)
                visited.add(b)
        if len(group) > 1:
            image_groups.append(group)

    return {"exact": exact, "text": text_groups, "image": image_groups}


def summarize_duplicate_directories(
    duplicate_groups: Iterable[Iterable[str]],
    all_paths: Optional[Iterable[str]] = None,
    min_shared: int = 1,
) -> List[Dict[str, Any]]:
    """Aggregate file-level duplicate groups into directory-pair overlap counts.

    Answers "are these two folders near-duplicates of each other?" from a
    duplicate-file report without reading every individual file pair — a
    report that can balloon to tens of thousands of lines / megabytes of
    output on a dataset with thousands of duplicate files (e.g. a dataset
    export nested inside its own augmented copy), which is expensive for an
    agent to page through and often the *real* question being asked.

    For each duplicate group, every pair of distinct parent directories
    among its files gets its shared-file count incremented by one. The
    result is a compact, directory-count-sized report (not file-count-sized)
    regardless of how many duplicate files exist.

    Args:
    ----
        duplicate_groups: Groups of duplicate file paths, e.g. from
            ``find_duplicates(...)["exact"]``.
        all_paths: Optional full list of scanned paths (not just
            duplicates), used to compute each directory's total file count
            so an ``overlap_pct`` can be reported alongside the raw
            shared-file count. If omitted, the ``*_total_files``/
            ``overlap_pct`` fields are left as ``None``.
        min_shared: Only report directory pairs sharing at least this many
            duplicate files (default 1 — every pair found).

    Returns:
    -------
        A list of dicts, one per directory pair, sorted by ``shared_files``
        descending: ``{"dir_a", "dir_b", "shared_files", "dir_a_total_files",
        "dir_b_total_files", "overlap_pct"}``. ``overlap_pct`` is
        ``shared_files / min(dir_a_total_files, dir_b_total_files) * 100``,
        rounded to 1 decimal (``None`` if ``all_paths`` wasn't given, or
        either directory's total is unknown/zero).

    """
    pair_counts: Dict[Tuple[str, str], int] = defaultdict(int)
    for group in duplicate_groups:
        dirs = sorted({str(Path(p).parent) for p in group})
        for dir_a, dir_b in combinations(dirs, 2):
            pair_counts[(dir_a, dir_b)] += 1

    dir_totals: Dict[str, int] = {}
    if all_paths is not None:
        dir_totals = dict(Counter(str(Path(p).parent) for p in all_paths))

    results: List[Dict[str, Any]] = []
    for (dir_a, dir_b), shared in pair_counts.items():
        if shared < min_shared:
            continue
        total_a = dir_totals.get(dir_a)
        total_b = dir_totals.get(dir_b)
        overlap_pct = round(shared / min(total_a, total_b) * 100, 1) if total_a and total_b else None
        results.append(
            {
                "dir_a": dir_a,
                "dir_b": dir_b,
                "shared_files": shared,
                "dir_a_total_files": total_a,
                "dir_b_total_files": total_b,
                "overlap_pct": overlap_pct,
            }
        )

    results.sort(key=lambda r: r["shared_files"], reverse=True)
    return results


if __name__ == "__main__":
    # quick smoke demo when run directly
    import sys

    paths = sys.argv[1:]
    if not paths:
        print("Usage: dedup.py file1 file2 ...")
    else:
        res = find_duplicates(paths)
        print(res)
