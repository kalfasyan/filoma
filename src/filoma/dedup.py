"""Duplicate detection and similarity helpers for files.

This module provides:
- exact file hashing (`compute_sha256`)
- text shingles + Jaccard similarity (`text_shingles`, `jaccard_similarity`)
- optional MinHash if `datasketch` is installed (`minhash_signature`)
- image perceptual hashes: aHash and dHash (`ahash_image`, `dhash_image`) using Pillow when available
- high-level `find_duplicates` that can detect exact, near-duplicate text and image files

The implementation avoids hard dependencies; Pillow and datasketch are optional.
"""

from __future__ import annotations

import hashlib
import os
import re
from collections import defaultdict
from typing import Dict, Iterable, List, Set

try:
    from PIL import Image
except Exception:  # pragma: no cover - PIL optional
    Image = None

try:
    from datasketch import MinHash
except Exception:  # pragma: no cover - datasketch optional
    MinHash = None


def compute_sha256(path: str, block_size: int = 65536) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(block_size), b""):
            h.update(block)
    return h.hexdigest()


def file_fingerprint(path: str) -> Dict[str, object]:
    st = os.stat(path)
    return {"path": path, "size": st.st_size, "mtime": st.st_mtime, "sha256": compute_sha256(path)}


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
    tokens = _normalize_tokens(text)
    if len(tokens) < k:
        return set([" ".join(tokens)])
    return set(" ".join(tokens[i : i + k]) for i in range(len(tokens) - k + 1))


def jaccard_similarity(a: Set[str], b: Set[str]) -> float:
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
    sig = sorted(int(hashlib.sha1(s.encode("utf8")).hexdigest()[:8], 16) for s in shingles)
    return sig


def _int_to_hex(i: int, width: int = 16) -> str:
    return f"{i:0{width}x}"


def _hamming_int(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def ahash_image(path: str, hash_size: int = 8) -> str:
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
    a = int(a_hex, 16)
    b = int(b_hex, 16)
    return _hamming_int(a, b)


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tif", ".tiff", ".webp"}


def is_image_path(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in IMAGE_EXTS


def find_duplicates(
    paths: Iterable[str],
    mode: str = "auto",
    text_k: int = 3,
    text_threshold: float = 0.8,
    image_hash: str = "ahash",
    image_max_distance: int = 5,
) -> Dict[str, List[List[str]]]:
    """Find duplicates among `paths`.

    Returns a dict with keys `exact`, `text`, `image` containing lists of groups.

    - `mode`: 'auto' (choose by extension), 'exact', 'text', 'image', or 'mixed'.
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


if __name__ == "__main__":
    # quick smoke demo when run directly
    import sys

    paths = sys.argv[1:]
    if not paths:
        print("Usage: dedup.py file1 file2 ...")
    else:
        res = find_duplicates(paths)
        print(res)
