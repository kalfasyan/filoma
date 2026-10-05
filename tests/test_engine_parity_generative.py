"""Generative differential tests for the scan engines.

Hand-written parity tests (``test_rust_dua_core.py`` and friends) compare engines
on a few fixed trees. This module instead builds *random* trees (nested and empty
directories, hidden entries, zero-byte files, odd names, symlinks of every kind,
files directly in the root) and compares each engine against an independent
``os.scandir`` oracle that implements the "Engine harmonization contract" from
``docs/reference/architecture.md``:

- symlinks (``follow_links=False``) are neither counted nor traversed;
- the root counts as a folder at depth 0; with ``max_depth=N`` folders deeper than
  N are not counted and files directly inside counted folders are;
- a folder is empty iff ``scandir`` yields no entries (hidden-only children make it
  non-empty even when hidden entries are filtered out);
- ``search_hidden=False`` skips dot-entries *and everything beneath dot-directories*.

Seeds are fixed so failures are reproducible: re-run a single case with
``pytest "tests/test_engine_parity_generative.py::test_rust_engine_matches_oracle[<engine>-<seed>]"``.
"""

import os
import random
import stat
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Set

import pytest

from filoma.directories import DirectoryProfiler, DirectoryProfilerConfig
from filoma.directories.directory_profiler import FD_AVAILABLE

try:
    from filoma.filoma_core import (
        probe_directory_rust,
        probe_directory_rust_async,
        probe_directory_rust_dua_core,
        probe_directory_rust_parallel,
    )

    RUST_AVAILABLE = True
except ImportError:
    RUST_AVAILABLE = False

SEEDS = list(range(40))
NO_EXTENSION = "<no extension>"

_DIR_STEMS = ["src", "data", "images", "docs", "train", "val", "test", ".hidden", ".cache", "with space", "UPPER", "dotted.name", "résumé"]
_FILE_STEMS = ["file", "IMG", "noext", "archive", "data", "notes", "report", "café"]
_FILE_EXTS = ["", ".txt", ".TXT", ".csv", ".jpg", ".JPG", ".tar.gz", ".bin", ".md"]


# ---------------------------------------------------------------------------
# Random tree generation
# ---------------------------------------------------------------------------


def build_random_tree(root: Path, rng: random.Random, symlinks: bool = True, hidden: bool = True) -> None:
    """Populate ``root`` with a random tree. Deterministic for a given ``rng`` state."""
    counter = 0

    def unique(prefix: str) -> str:
        nonlocal counter
        counter += 1
        return f"{prefix}{counter}"

    def dir_stem() -> str:
        stem = rng.choice(_DIR_STEMS)
        while not hidden and stem.startswith("."):
            stem = rng.choice(_DIR_STEMS)
        return stem

    dirs: List[Path] = [root]
    depth_of: Dict[Path, int] = {root: 0}

    # Top-level directories: the parallel walkdir engine only engages with several of them.
    for _ in range(rng.randint(1, 8)):
        d = root / unique(dir_stem())
        d.mkdir()
        dirs.append(d)
        depth_of[d] = 1

    for _ in range(rng.randint(0, 15)):
        parent = rng.choice(dirs)
        if depth_of[parent] >= 5:
            continue
        d = parent / unique(dir_stem())
        d.mkdir()
        dirs.append(d)
        depth_of[d] = depth_of[parent] + 1

    files: List[Path] = []
    for _ in range(rng.randint(0, 40)):
        parent = rng.choice(dirs)  # includes the root itself
        if hidden and rng.random() < 0.15:
            name = unique(".dot")
        else:
            name = unique(rng.choice(_FILE_STEMS)) + rng.choice(_FILE_EXTS)
        size = 0 if rng.random() < 0.2 else rng.randint(1, 300)
        f = parent / name
        f.write_bytes(b"x" * size)
        files.append(f)

    if hidden and rng.random() < 0.5:  # a directory whose only child is hidden
        d = root / unique("hiddenonly")
        d.mkdir()
        (d / ".secret").write_bytes(b"s")
        dirs.append(d)
    if rng.random() < 0.3:  # an empty directory, explicitly
        (root / unique("empty")).mkdir()

    if symlinks:
        try:
            for _ in range(rng.randint(0, 4)):
                kind = rng.choice(["file", "dir", "broken", "loop"])
                parent = rng.choice(dirs)
                link = parent / unique("link")
                if kind == "file" and files:
                    os.symlink(rng.choice(files), link)
                elif kind == "dir":
                    os.symlink(rng.choice(dirs), link)
                elif kind == "broken":
                    os.symlink(root / "does-not-exist", link)
                elif kind == "loop":
                    os.symlink(parent.parent if parent != root else root, link)
            if rng.random() < 0.3:  # a directory whose only child is a symlink
                d = root / unique("linkonly")
                d.mkdir()
                os.symlink(root / "does-not-exist", d / "l")
        except (OSError, NotImplementedError):
            pytest.skip("symlinks not supported on this platform")


# ---------------------------------------------------------------------------
# Oracle
# ---------------------------------------------------------------------------


def reference_scan(root: Path, max_depth: Optional[int] = None, search_hidden: bool = True) -> Dict:
    """Independent implementation of the harmonization contract using ``os.scandir``."""
    files = 0
    folders = 0
    size = 0
    deepest = 0
    extensions: Counter = Counter()
    depths: Counter = Counter()
    empty: Set[str] = set()
    paths: Set[str] = set()

    def walk(dirpath: Path, depth: int) -> None:
        nonlocal files, folders, size, deepest
        folders += 1
        deepest = max(deepest, depth)
        depths[depth] += 1
        with os.scandir(dirpath) as it:
            entries = list(it)
        if not entries:
            empty.add(os.path.relpath(dirpath, root))
        for entry in entries:
            if not search_hidden and entry.name.startswith("."):
                continue
            mode = entry.stat(follow_symlinks=False).st_mode
            if stat.S_ISDIR(mode):
                if max_depth is None or depth + 1 <= max_depth:
                    paths.add(os.path.relpath(entry.path, root))
                    walk(Path(entry.path), depth + 1)
            elif stat.S_ISREG(mode):
                files += 1
                size += entry.stat(follow_symlinks=False).st_size
                extensions[Path(entry.name).suffix.lower() or NO_EXTENSION] += 1
                paths.add(os.path.relpath(entry.path, root))

    walk(root, 0)
    return {
        "files": files,
        "folders": folders,
        "size": size,
        "max_depth": deepest,
        "extensions": dict(extensions),
        "depth_distribution": dict(depths),
        "empty": empty,
        "paths": paths,
    }


def normalize(root: Path, raw: Dict, with_paths: bool = True) -> Dict:
    """Project an engine's raw result dict onto the fields the contract covers."""
    summary = raw["summary"]
    out = {
        "files": summary["total_files"],
        "folders": summary["total_folders"],
        "size": summary["total_size_bytes"],
        "max_depth": summary["max_depth"],
        "extensions": dict(raw["file_extensions"]),
        "depth_distribution": {int(k): v for k, v in raw["depth_distribution"].items()},
        "empty": {os.path.relpath(p, root) for p in raw["empty_folders"]},
    }
    # Each folder (the root included) must be keyed exactly once in the per-folder file counts.
    top_keys = [os.path.relpath(p, root) for p, _ in raw["top_folders_by_file_count"]]
    assert len(top_keys) == len(set(top_keys)), f"duplicate folder keys in top_folders_by_file_count: {top_keys}"
    if with_paths and "paths" in raw:
        out["paths"] = {os.path.relpath(p, root) for p in raw["paths"]}
    return out


def assert_matches(actual: Dict, expected: Dict) -> None:
    """Compare field by field so a failure names exactly what differs."""
    for key in actual:
        a, e = actual[key], expected[key]
        if isinstance(a, set):
            assert a == e, f"{key}: missing={sorted(e - a)[:5]} unexpected={sorted(a - e)[:5]}"
        else:
            assert a == e, f"{key}: engine={a!r} oracle={e!r}"


# ---------------------------------------------------------------------------
# Engines under test
# ---------------------------------------------------------------------------


def _walkdir_sequential(path: str, max_depth, search_hidden):
    return probe_directory_rust(path, max_depth=max_depth, search_hidden=search_hidden, return_paths=True)


def _walkdir_parallel(path: str, max_depth, search_hidden):
    # parallel_threshold=0 lets the true parallel engine engage (it still needs several top-level dirs).
    return probe_directory_rust_parallel(path, max_depth=max_depth, parallel_threshold=0, search_hidden=search_hidden, return_paths=True)


def _dua_core(path: str, max_depth, search_hidden):
    return probe_directory_rust_dua_core(path, max_depth=max_depth, search_hidden=search_hidden, return_paths=True)


def _async(path: str, max_depth, search_hidden):
    # A small worker pool keeps the async engine's per-scan startup/shutdown cost low in tests.
    return probe_directory_rust_async(path, max_depth=max_depth, search_hidden=search_hidden, return_paths=True, concurrency_limit=4)


RUST_ENGINES = {
    "walkdir-sequential": _walkdir_sequential,
    "walkdir-parallel": _walkdir_parallel,
    "dua-core": _dua_core,
    "async": _async,
}

MAX_DEPTHS = [None, 0, 1, 2, 3]


@pytest.mark.skipif(not RUST_AVAILABLE, reason="Rust extension not available")
@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("engine", sorted(RUST_ENGINES))
def test_rust_engine_matches_oracle(engine, seed, tmp_path):
    """Every Rust engine agrees with the oracle for all max_depth / hidden combinations."""
    rng = random.Random(seed)
    build_random_tree(tmp_path, rng)

    for max_depth in MAX_DEPTHS:
        for search_hidden in (True, False):
            expected = reference_scan(tmp_path, max_depth=max_depth, search_hidden=search_hidden)
            raw = RUST_ENGINES[engine](str(tmp_path), max_depth, search_hidden)
            try:
                assert_matches(normalize(tmp_path, raw), expected)
            except AssertionError as exc:
                raise AssertionError(f"engine={engine} seed={seed} max_depth={max_depth} search_hidden={search_hidden}: {exc}") from None


@pytest.mark.parametrize("seed", SEEDS)
def test_python_backend_matches_oracle(seed, tmp_path):
    """The pure-Python backend agrees with the oracle (it always includes hidden entries)."""
    rng = random.Random(seed)
    build_random_tree(tmp_path, rng)

    for max_depth in MAX_DEPTHS:
        expected = reference_scan(tmp_path, max_depth=max_depth, search_hidden=True)
        config = DirectoryProfilerConfig(search_backend="python", show_progress=False)
        analysis = DirectoryProfiler(config).probe(str(tmp_path), max_depth=max_depth).to_dict()
        try:
            assert_matches(normalize(tmp_path, analysis, with_paths=False), {k: v for k, v in expected.items() if k != "paths"})
        except AssertionError as exc:
            raise AssertionError(f"python backend seed={seed} max_depth={max_depth}: {exc}") from None


@pytest.mark.skipif(not FD_AVAILABLE, reason="fd is not installed")
@pytest.mark.parametrize("seed", SEEDS)
def test_fd_backend_matches_oracle(seed, tmp_path):
    """fd agrees with the oracle on trees without hidden entries (fd hides dot-entries by design)."""
    rng = random.Random(seed)
    build_random_tree(tmp_path, rng, hidden=False)

    for max_depth in MAX_DEPTHS:
        expected = reference_scan(tmp_path, max_depth=max_depth, search_hidden=True)
        config = DirectoryProfilerConfig(search_backend="fd", show_progress=False)
        analysis = DirectoryProfiler(config).probe(str(tmp_path), max_depth=max_depth).to_dict()
        try:
            assert_matches(normalize(tmp_path, analysis, with_paths=False), {k: v for k, v in expected.items() if k != "paths"})
        except AssertionError as exc:
            raise AssertionError(f"fd backend seed={seed} max_depth={max_depth}: {exc}") from None


# ---------------------------------------------------------------------------
# Readable regression tests for bugs the generative tests originally found
# ---------------------------------------------------------------------------


@pytest.fixture
def root_files_tree(tmp_path):
    """Four top-level directories (enough to engage the parallel walkdir engine) plus files directly in the root."""
    for name in ("train", "val", "test", "extra"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "x.txt").write_text("1")
    (tmp_path / "labels.csv").write_text("a" * 1000)
    (tmp_path / "README.md").write_text("b" * 500)
    return tmp_path


@pytest.mark.skipif(not RUST_AVAILABLE, reason="Rust extension not available")
@pytest.mark.parametrize("engine", sorted(RUST_ENGINES))
def test_files_directly_in_root_are_counted(engine, root_files_tree):
    """The parallel walkdir engine used to drop root-level files (and their bytes) when it engaged."""
    summary = RUST_ENGINES[engine](str(root_files_tree), None, True)["summary"]
    assert summary["total_files"] == 6
    assert summary["total_size_bytes"] == 1504


@pytest.mark.skipif(not RUST_AVAILABLE, reason="Rust extension not available")
def test_profiler_walkdir_parallel_counts_root_files(root_files_tree):
    """Same bug through the public API (``walker='walkdir'`` is a documented opt-in)."""
    config = DirectoryProfilerConfig(use_rust=True, use_parallel=True, walker="walkdir", parallel_threshold=0, show_progress=False)
    summary = DirectoryProfiler(config).probe(str(root_files_tree)).to_dict()["summary"]
    assert (summary["total_files"], summary["total_size_bytes"]) == (6, 1504)


@pytest.mark.skipif(not RUST_AVAILABLE, reason="Rust extension not available")
@pytest.mark.parametrize("engine", sorted(RUST_ENGINES))
def test_root_folder_is_keyed_once(engine, root_files_tree):
    """dua-core used to list the root twice in top_folders_by_file_count (once with 0 files)."""
    raw = RUST_ENGINES[engine](str(root_files_tree), None, True)
    keys = [os.path.relpath(p, root_files_tree) for p, _ in raw["top_folders_by_file_count"]]
    assert keys.count(".") == 1
    assert dict(zip(keys, (n for _, n in raw["top_folders_by_file_count"])))["."] == 2


@pytest.mark.skipif(not RUST_AVAILABLE, reason="Rust extension not available")
def test_async_engine_counts_empty_folders_once(tmp_path):
    """The async engine used to count every empty directory twice and report folder depths off by one."""
    (tmp_path / "a" / "b").mkdir(parents=True)
    (tmp_path / "empty").mkdir()
    (tmp_path / "a" / "b" / "c.txt").write_text("1")

    raw = _async(str(tmp_path), None, True)
    assert raw["summary"]["total_folders"] == 4  # root, a, a/b, empty
    assert raw["summary"]["max_depth"] == 2
    assert {int(k): v for k, v in raw["depth_distribution"].items()} == {0: 1, 1: 2, 2: 1}
    assert {os.path.relpath(p, tmp_path) for p in raw["empty_folders"]} == {"empty"}


@pytest.mark.skipif(not RUST_AVAILABLE, reason="Rust extension not available")
@pytest.mark.parametrize("engine", sorted(RUST_ENGINES))
def test_search_hidden_false_prunes_hidden_directories(engine, tmp_path):
    """Dot-directories are skipped together with their contents (files inside them used to be counted)."""
    (tmp_path / ".git" / "objects").mkdir(parents=True)
    (tmp_path / ".git" / "objects" / "abc123").write_text("blob")
    (tmp_path / "keep.txt").write_text("x")

    summary = RUST_ENGINES[engine](str(tmp_path), None, False)["summary"]
    assert summary["total_files"] == 1
    assert summary["total_folders"] == 1


@pytest.mark.skipif(not RUST_AVAILABLE, reason="Rust extension not available")
def test_sequential_max_depth_counts_leaf_folders(tmp_path):
    """The sequential engine reported max_depth from entry depth - 1, so a deepest empty folder was one level short."""
    (tmp_path / "a" / "b" / "c").mkdir(parents=True)

    for engine in ("walkdir-sequential", "dua-core"):
        assert RUST_ENGINES[engine](str(tmp_path), None, True)["summary"]["max_depth"] == 3, engine
