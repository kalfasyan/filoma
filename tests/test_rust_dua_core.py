#!/usr/bin/env python3
"""Tests for the dua-core (parallel walker) Rust engine.

Validates parity with the walkdir-based parallel engine, config validation,
and backend selection behavior for the ``walker`` option.
"""

import tempfile
from pathlib import Path

import pytest

from filoma.directories import DirectoryProfiler, DirectoryProfilerConfig

try:
    from filoma.filoma_core import (
        probe_directory_rust,
        probe_directory_rust_dua_core,
        probe_directory_rust_parallel,
    )

    RUST_ENGINES_AVAILABLE = True
except ImportError:
    RUST_ENGINES_AVAILABLE = False

pytestmark = pytest.mark.skipif(not RUST_ENGINES_AVAILABLE, reason="Rust extension not available")


@pytest.fixture
def test_directory():
    """Complex test directory (mirrors test_backend_comprehensive)."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        dirs = [
            "docs",
            "docs/images",
            "src",
            "src/modules",
            "tests",
            "empty_dir",
            "data",
            ".hidden",
        ]
        for dir_name in dirs:
            (tmp_path / dir_name).mkdir(parents=True, exist_ok=True)

        files = {
            "docs/README.md": "# Project\nThis is a test project.",
            "docs/guide.txt": "User guide content here.",
            "docs/images/logo.png": "fake png data" * 10,
            "docs/images/diagram.jpg": "fake jpg data" * 20,
            "src/main.py": "def main():\n    print('hello')\n\nif __name__ == '__main__':\n    main()",
            "src/utils.py": "def helper():\n    return True",
            "src/modules/__init__.py": "",
            "src/modules/core.py": "class Core:\n    pass",
            "src/modules/helpers.rs": "fn helper() -> bool { true }",
            "tests/test_main.py": "def test_main():\n    assert True",
            "tests/test_utils.py": "def test_helper():\n    assert True",
            "data/large_file.txt": "x" * 1000,
            "data/small.json": '{"key": "value"}',
            ".hidden/secret.txt": "secret content",
        }

        for file_path, content in files.items():
            (tmp_path / file_path).write_text(content)

        yield str(tmp_path)


def _probe_dua(path, **kwargs):
    return probe_directory_rust_dua_core(path, **kwargs)


def _probe_parallel(path, **kwargs):
    # parallel_threshold=0 forces the true parallel walkdir engine; with the
    # default (None) the Rust prober falls back to the sequential engine.
    return probe_directory_rust_parallel(path, parallel_threshold=0, **kwargs)


class TestDuaCoreParity:
    """Parity between the dua-core engine and the walkdir parallel engine."""

    def test_basic_parity(self, test_directory):
        dua = _probe_dua(test_directory)
        parallel = _probe_parallel(test_directory)

        assert dua["summary"]["total_files"] == parallel["summary"]["total_files"]
        assert dua["summary"]["total_folders"] == parallel["summary"]["total_folders"]
        assert dua["summary"]["total_size_bytes"] == parallel["summary"]["total_size_bytes"]
        assert dua["summary"]["max_depth"] == parallel["summary"]["max_depth"]
        assert dua["file_extensions"] == parallel["file_extensions"]
        assert dua["depth_distribution"] == parallel["depth_distribution"]

    def test_empty_folder_detection(self, test_directory):
        dua = _probe_dua(test_directory)
        parallel = _probe_parallel(test_directory)

        assert dua["summary"]["empty_folder_count"] == parallel["summary"]["empty_folder_count"]
        dua_empty = sorted(Path(p).name for p in dua["empty_folders"])
        parallel_empty = sorted(Path(p).name for p in parallel["empty_folders"])
        assert dua_empty == parallel_empty
        assert "empty_dir" in dua_empty

    def test_files_per_folder_parity(self, test_directory):
        dua = _probe_dua(test_directory)
        parallel = _probe_parallel(test_directory)

        dua_top = {(Path(p).name, count) for p, count in dua["top_folders_by_file_count"]}
        parallel_top = {(Path(p).name, count) for p, count in parallel["top_folders_by_file_count"]}
        assert dua_top == parallel_top

    def test_max_depth_parity(self, test_directory):
        # The canonical max_depth contract is the sequential engine's (which
        # is also what the Python backend enforces): files at depth <= max_depth + 1
        # are included, directories at depth > max_depth are not counted.
        for max_depth in (1, 2, 3):
            dua = _probe_dua(test_directory, max_depth=max_depth)
            sequential = probe_directory_rust(test_directory, max_depth=max_depth, search_hidden=True)
            assert dua["summary"]["total_files"] == sequential["summary"]["total_files"], f"max_depth={max_depth}"
            assert dua["summary"]["total_folders"] == sequential["summary"]["total_folders"], f"max_depth={max_depth}"
            assert dua["summary"]["max_depth"] == sequential["summary"]["max_depth"], f"max_depth={max_depth}"

    def test_hidden_filtering_parity(self, test_directory):
        dua = _probe_dua(test_directory, search_hidden=False)
        parallel = _probe_parallel(test_directory, search_hidden=False)
        assert dua["summary"]["total_files"] == parallel["summary"]["total_files"]
        assert dua["summary"]["total_folders"] == parallel["summary"]["total_folders"]
        assert all(".hidden" not in str(p) for p in dua["empty_folders"])

    def test_hidden_only_children_not_empty(self):
        # A visible directory containing only hidden entries is NOT empty,
        # even when search_hidden=False (parity with the read_dir-based check).
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            (tmp_path / "visible").mkdir()
            (tmp_path / "visible" / ".secret").write_text("hidden content")

            dua = _probe_dua(tmp_dir, search_hidden=False)
            parallel = _probe_parallel(tmp_dir, search_hidden=False)
            assert dua["summary"]["total_folders"] == parallel["summary"]["total_folders"]
            assert dua["summary"]["empty_folder_count"] == parallel["summary"]["empty_folder_count"]
            dua_empty = sorted(Path(p).name for p in dua["empty_folders"])
            assert "visible" not in dua_empty

    def test_fast_path_parity(self, test_directory):
        dua = _probe_dua(test_directory, fast_path_only=True)
        parallel = _probe_parallel(test_directory, fast_path_only=True)
        assert dua["summary"]["total_files"] == parallel["summary"]["total_files"]
        assert dua["summary"]["total_folders"] == parallel["summary"]["total_folders"]
        assert dua["summary"]["total_size_bytes"] == 0
        assert parallel["summary"]["total_size_bytes"] == 0

    def test_max_depth_linear_chain(self):
        # Mirrors tests/directories/test_directory_profiler.py: max_depth=2
        # must exclude the level3 directory and everything under it.
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            (tmp_path / "level1" / "level2" / "level3").mkdir(parents=True)
            (tmp_path / "level1" / "file1.txt").write_text("test")
            (tmp_path / "level1" / "level2" / "file2.txt").write_text("test")
            (tmp_path / "level1" / "level2" / "level3" / "file3.txt").write_text("test")

            dua = _probe_dua(tmp_dir, max_depth=2)
            assert dua["summary"]["total_files"] == 2
            assert dua["summary"]["total_folders"] == 3
            assert dua["summary"]["max_depth"] == 2

    def test_empty_root_directory(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            dua = _probe_dua(tmp_dir)
            parallel = _probe_parallel(tmp_dir)
            assert dua["summary"]["total_files"] == parallel["summary"]["total_files"] == 0
            assert dua["summary"]["total_folders"] == parallel["summary"]["total_folders"]
            assert dua["summary"]["empty_folder_count"] == parallel["summary"]["empty_folder_count"]

    def test_directory_with_only_subdirectories(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            (tmp_path / "sub_only").mkdir()
            (tmp_path / "mixed" / "leaf").mkdir(parents=True)
            (tmp_path / "mixed" / "leaf" / "file.txt").write_text("x")

            dua = _probe_dua(tmp_dir)
            parallel = _probe_parallel(tmp_dir)
            assert dua["summary"]["total_files"] == parallel["summary"]["total_files"]
            assert dua["summary"]["total_folders"] == parallel["summary"]["total_folders"]

            dua_empty = sorted(Path(p).name for p in dua["empty_folders"])
            parallel_empty = sorted(Path(p).name for p in parallel["empty_folders"])
            assert dua_empty == parallel_empty
            assert "sub_only" in dua_empty
            assert "leaf" not in dua_empty

    def test_invalid_paths(self):
        with pytest.raises(Exception):
            _probe_dua("/nonexistent/path/that/does/not/exist")
        with tempfile.NamedTemporaryFile() as f:
            with pytest.raises(Exception):
                _probe_dua(f.name)

    def test_return_paths(self, test_directory):
        dua = _probe_dua(test_directory)
        with_paths = _probe_dua(test_directory, return_paths=True)
        # Root is excluded from paths (matches rglob-based DataFrame collection).
        expected = dua["summary"]["total_files"] + dua["summary"]["total_folders"] - 1
        assert len(with_paths["paths"]) == expected
        assert len(set(with_paths["paths"])) == expected  # no duplicates
        assert any(p.endswith("README.md") for p in with_paths["paths"])
        assert not any(Path(p) == Path(test_directory) for p in with_paths["paths"])

    def test_return_paths_max_depth(self, test_directory):
        with_paths = _probe_dua(test_directory, max_depth=1, return_paths=True)
        root = Path(test_directory)
        for p in with_paths["paths"]:
            rel = Path(p).relative_to(root).parts
            assert len(rel) <= 2, p


class TestDuaCoreSelection:
    """walker config routing in DirectoryProfiler."""

    def test_walker_auto_uses_dua_core_on_local(self, test_directory):
        profiler = DirectoryProfiler(DirectoryProfilerConfig(search_backend="rust", show_progress=False))
        result = profiler.probe(test_directory)
        assert profiler._rust_engine_used == "dua-core"
        assert result["summary"]["total_files"] >= 12
        assert result["summary"]["total_folders"] >= 8

    def test_walker_explicit_dua_core(self, test_directory):
        profiler = DirectoryProfiler(DirectoryProfilerConfig(search_backend="rust", walker="dua-core", show_progress=False))
        result = profiler.probe(test_directory)
        assert profiler._rust_engine_used == "dua-core"
        assert result["summary"]["total_files"] >= 12

    def test_walker_walkdir_disables_dua_core(self, test_directory):
        profiler = DirectoryProfiler(DirectoryProfilerConfig(search_backend="rust", walker="walkdir", show_progress=False))
        result = profiler.probe(test_directory)
        assert profiler._rust_engine_used == "walkdir"
        assert result["summary"]["total_files"] >= 12

    def test_use_parallel_false_uses_sequential(self, test_directory):
        # use_parallel=False must keep the sequential walkdir engine; the
        # dua-core engine is inherently parallel and must not override it.
        profiler = DirectoryProfiler(DirectoryProfilerConfig(search_backend="rust", use_parallel=False, show_progress=False))
        result = profiler.probe(test_directory)
        assert profiler._rust_engine_used == "walkdir"
        assert "Sequential" in profiler._get_impl_display_name("rust")
        assert result["summary"]["total_files"] >= 12

    def test_fast_path_routes_to_walkdir(self, test_directory):
        # The fast path routes to the walkdir engines because dua-core stats
        # every entry regardless of fast_path_only.
        profiler = DirectoryProfiler(DirectoryProfilerConfig(search_backend="rust", fast_path_only=True, show_progress=False))
        result = profiler.probe(test_directory)
        assert profiler._rust_engine_used == "walkdir"
        assert result["summary"]["total_size_bytes"] == 0

    def test_dua_core_unavailable_falls_back(self, test_directory, monkeypatch):
        monkeypatch.setattr("filoma.directories.directory_profiler.RUST_DUA_CORE_AVAILABLE", False)
        profiler = DirectoryProfiler(DirectoryProfilerConfig(search_backend="rust", walker="dua-core", show_progress=False))
        result = profiler.probe(test_directory)
        assert profiler._rust_engine_used == "walkdir"
        assert result["summary"]["total_files"] >= 12

    def test_walker_threads_validation(self):
        with pytest.raises(ValueError):
            DirectoryProfilerConfig(walker_threads=0)
        with pytest.raises(ValueError):
            DirectoryProfilerConfig(walker_threads=-1)
        with pytest.raises(ValueError):
            DirectoryProfilerConfig(walker_threads=513)
        with pytest.raises(ValueError):
            DirectoryProfilerConfig(walker="bogus")

    def test_walker_threads_accepted(self, test_directory):
        profiler = DirectoryProfiler(DirectoryProfilerConfig(search_backend="rust", walker="dua-core", walker_threads=2, show_progress=False))
        result = profiler.probe(test_directory)
        assert profiler._rust_engine_used == "dua-core"
        assert result["summary"]["total_files"] >= 12

    def test_implementation_info(self):
        profiler = DirectoryProfiler(DirectoryProfilerConfig(search_backend="rust", show_progress=False))
        info = profiler.get_implementation_info()
        assert info["walker"] == "auto"
        assert info["rust_dua_core_available"] is True


class TestDuaCoreProbeToDf:
    """probe_to_df must use the Rust-returned paths, not a second rglob."""

    def test_probe_to_df_uses_dua_paths(self, test_directory):
        import filoma as flm

        df = flm.probe_to_df(test_directory, search_backend="rust", walker="dua-core", enrich=False)
        probe = flm.probe(test_directory, search_backend="rust", walker="dua-core")
        # Root is excluded from the DataFrame (rglob semantics).
        expected = probe["summary"]["total_files"] + probe["summary"]["total_folders"] - 1
        assert len(df) == expected

    def test_probe_to_df_matches_walkdir_rows(self, test_directory):
        import filoma as flm

        df_dua = flm.probe_to_df(test_directory, search_backend="rust", walker="dua-core", enrich=False)
        df_walkdir = flm.probe_to_df(test_directory, search_backend="rust", walker="walkdir", enrich=False)
        assert len(df_dua) == len(df_walkdir)
