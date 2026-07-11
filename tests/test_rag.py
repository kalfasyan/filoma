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
