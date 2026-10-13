import tempfile
from pathlib import Path

import pytest

from filoma.core.rag import RagStore, _chunk_text, _is_text_file, _resolve_embedder


def test_is_text_file_recognizes_known_types():
    assert _is_text_file(Path("doc.txt"))
    assert _is_text_file(Path("doc.md"))
    assert _is_text_file(Path("doc.json"))
    assert _is_text_file(Path("doc.py"))
    assert not _is_text_file(Path("image.png"))
    assert not _is_text_file(Path("video.mp4"))


def test_chunk_text_short_input():
    chunks = _chunk_text("Hello world.")
    assert len(chunks) >= 1
    assert "Hello world" in chunks[0]


def test_chunk_text_long_input():
    long_text = "This is sentence one. " * 300 + "This is sentence two. " * 300
    chunks = _chunk_text(long_text, max_tokens=64)
    assert len(chunks) > 1


def test_chunk_text_sentence_boundary():
    text = "First sentence. Second sentence! Third sentence? Final sentence."
    chunks = _chunk_text(text, max_tokens=2)
    assert len(chunks) > 1


def test_index_and_search(tmp_path):
    try:
        import lancedb  # noqa: F401
    except ModuleNotFoundError:
        pytest.skip("LanceDB not installed")

    tmp_path = Path(tmp_path)
    (tmp_path / "readme.md").write_text("# Test Project\n\nThis is a test document about machine learning.\n")
    (tmp_path / "notes.txt").write_text("Notes about dataset cleaning and preprocessing.\n")

    with tempfile.TemporaryDirectory() as db_dir:
        store = RagStore(db_path=db_dir)
        try:
            count = store.index(str(tmp_path))
            assert count >= 1
        except (ImportError, RuntimeError) as e:
            pytest.skip(f"LanceDB or embeddings unavailable: {e}")

        try:
            results = store.search("machine learning", top_k=3)
        except (ImportError, RuntimeError) as e:
            pytest.skip(f"Search unavailable: {e}")

        assert len(results) >= 1


def test_search_empty_store(tmp_path):
    try:
        import lancedb  # noqa: F401
    except ModuleNotFoundError:
        pytest.skip("LanceDB not installed")

    with tempfile.TemporaryDirectory() as db_dir:
        store = RagStore(db_path=db_dir)
        results = store.search("anything")
        assert results == []


def test_index_nonexistent_directory(tmp_path):
    try:
        import lancedb  # noqa: F401
    except ModuleNotFoundError:
        pytest.skip("LanceDB not installed")

    with tempfile.TemporaryDirectory() as db_dir:
        store = RagStore(db_path=db_dir)
        with pytest.raises(FileNotFoundError):
            store.index("/nonexistent/path/12345")


def test_incremental_reindex_skips_unchanged(tmp_path):
    try:
        import lancedb  # noqa: F401
    except ModuleNotFoundError:
        pytest.skip("LanceDB not installed")

    tmp_path = Path(tmp_path)
    (tmp_path / "doc.txt").write_text("Some content here.")

    with tempfile.TemporaryDirectory() as db_dir:
        store = RagStore(db_path=db_dir)
        count1 = store.index(str(tmp_path))
        assert count1 >= 1

        count2 = store.index(str(tmp_path))
        assert count2 <= count1


def test_ragstore_close(tmp_path):
    try:
        import lancedb  # noqa: F401
    except ModuleNotFoundError:
        pytest.skip("LanceDB not installed")

    with tempfile.TemporaryDirectory() as db_dir:
        store = RagStore(db_path=db_dir)
        store.close()


def test_embedder_resolution():
    try:
        fn = _resolve_embedder()
        assert callable(fn)
    except ImportError:
        pytest.skip("No embedding backend available")


# ---------------------------------------------------------------------------
# Incremental indexing (pyarrow only; the "rag" extra does not install pandas)
# ---------------------------------------------------------------------------

_FAKE_EMBEDDER_SETUP = """
import hashlib
import filoma.core.rag as rag


def _fake_embedder():
    def embed(texts):
        return [[b / 255 for b in hashlib.sha256(t.encode()).digest()[:8]] for t in texts]

    return embed


rag._resolve_embedder = _fake_embedder
"""


def _store_with_fake_embedder(db_dir, monkeypatch):
    pytest.importorskip("lancedb")
    import hashlib

    import filoma.core.rag as rag

    def fake_embedder():
        return lambda texts: [[b / 255 for b in hashlib.sha256(t.encode()).digest()[:8]] for t in texts]

    monkeypatch.setattr(rag, "_resolve_embedder", fake_embedder)
    return rag.RagStore(db_path=str(db_dir))


def _rows(store):
    return store._db.open_table("filoma_chunks").to_arrow().column("path").to_pylist()


def test_incremental_reindex_adds_new_files_and_replaces_modified_ones(tmp_path, monkeypatch):
    """Adding a file used to crash (a DataFrame was passed to pyarrow.concat_tables); editing one duplicated its rows."""
    import os

    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "a.md").write_text("Notes about dataset cleaning. " * 5)
    (docs / "b.txt").write_text("Second file about embeddings. " * 5)
    store = _store_with_fake_embedder(tmp_path / "db", monkeypatch)

    assert store.index(str(docs)) == 2
    assert store.index(str(docs)) == 2  # unchanged files are skipped

    (docs / "c.md").write_text("A brand new file about migrations. " * 5)
    assert store.index(str(docs)) == 3
    assert sorted(_rows(store)) == ["a.md", "b.txt", "c.md"]

    (docs / "a.md").write_text("Rewritten notes with different content entirely. " * 5)
    os.utime(docs / "a.md", (1_900_000_000, 1_900_000_000))  # guarantee a new mtime
    assert store.index(str(docs)) == 3
    assert sorted(_rows(store)) == ["a.md", "b.txt", "c.md"], "the modified file must replace its old rows"


def test_reindex_works_without_pandas(tmp_path):
    """filoma[rag] (lancedb + sentence-transformers + pyarrow) does not install pandas; re-indexing used to crash there."""
    pytest.importorskip("lancedb")
    import subprocess
    import sys
    import textwrap

    code = (
        textwrap.dedent(
            """
            import sys

            class _NoPandas:
                def find_spec(self, name, path=None, target=None):
                    if name == "pandas" or name.startswith("pandas."):
                        raise ModuleNotFoundError(f"No module named {name!r}", name=name)

            sys.meta_path.insert(0, _NoPandas())
            for _m in [m for m in sys.modules if m == "pandas" or m.startswith("pandas.")]:
                del sys.modules[_m]
            """
        )
        + _FAKE_EMBEDDER_SETUP
        + textwrap.dedent(
            f"""
            from pathlib import Path

            docs = Path({str(tmp_path / "docs")!r})
            docs.mkdir()
            (docs / "a.md").write_text("Notes about dataset cleaning. " * 5)
            store = rag.RagStore(db_path={str(tmp_path / "db")!r})
            assert store.index(str(docs)) == 1
            assert store.index(str(docs)) == 1  # second run used to raise 'Table already exists'
            (docs / "b.md").write_text("Another file. " * 5)
            assert store.index(str(docs)) == 2
            """
        )
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=180)
    assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr[-1500:]}"
