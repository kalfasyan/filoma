"""Tests for DataFrame.add_embedding_cols / add_semantic_similarity_cols.

Uses a deterministic fake embedder (monkeypatched onto ``filoma.core.rag``)
so these tests don't require Ollama or sentence-transformers to be installed
or running.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest

from filoma.dataframe import DataFrame


def _fake_embed(texts):
    """Deterministic bag-of-words-ish embedding: vector of keyword hit counts."""
    keywords = ["machine", "learning", "cats", "dogs", "python"]
    vectors = []
    for text in texts:
        lower = text.lower()
        vectors.append([float(lower.count(k)) for k in keywords])
    return vectors


@pytest.fixture(autouse=True)
def patch_embedder(monkeypatch):
    monkeypatch.setattr("filoma.core.rag._resolve_embedder", lambda: _fake_embed)


@pytest.fixture
def sample_dir(tmp_path):
    (tmp_path / "ml_a.txt").write_text("Machine learning and learning about machines.")
    (tmp_path / "ml_b.md").write_text("More machine learning content here.")
    (tmp_path / "pets.txt").write_text("Cats and dogs are great pets, dogs especially.")
    (tmp_path / "image.png").write_bytes(b"\x89PNG\r\n\x1a\nnotarealpng")
    return tmp_path


def test_add_embedding_cols_adds_vectors_for_text_files(sample_dir):
    df = DataFrame(
        {
            "path": [
                str(sample_dir / "ml_a.txt"),
                str(sample_dir / "ml_b.md"),
                str(sample_dir / "pets.txt"),
                str(sample_dir / "image.png"),
            ]
        }
    )

    result = df.add_embedding_cols()

    assert "embedding" in result.columns
    embeddings = result._df["embedding"].to_list()
    # Text files get a non-null embedding of the expected dimensionality.
    assert embeddings[0] is not None and len(embeddings[0]) == 5
    assert embeddings[1] is not None
    assert embeddings[2] is not None
    # Binary file is skipped (not recognized as text).
    assert embeddings[3] is None


def test_add_embedding_cols_raises_on_missing_column():
    df = DataFrame({"other": ["a", "b"]})
    with pytest.raises(ValueError):
        df.add_embedding_cols()


def test_add_semantic_similarity_cols_finds_related_files(sample_dir):
    df = DataFrame(
        {
            "path": [
                str(sample_dir / "ml_a.txt"),
                str(sample_dir / "ml_b.md"),
                str(sample_dir / "pets.txt"),
            ]
        }
    )

    result = df.add_embedding_cols().add_semantic_similarity_cols(top_k=1)

    assert "nearest_neighbor_paths" in result.columns
    assert "nearest_neighbor_similarities" in result.columns

    rows = result._df.to_dicts()
    ml_a = next(r for r in rows if r["path"].endswith("ml_a.txt"))

    # The two machine-learning docs should be each other's nearest neighbor,
    # not the unrelated pets file.
    assert ml_a["nearest_neighbor_paths"][0].endswith("ml_b.md")


def test_add_semantic_similarity_cols_requires_embedding_column():
    df = DataFrame({"path": ["a.txt", "b.txt"]})
    with pytest.raises(ValueError):
        df.add_semantic_similarity_cols()


def test_add_semantic_similarity_cols_handles_single_row():
    df = DataFrame({"path": ["a.txt"], "embedding": [[1.0, 0.0]]})
    result = df.add_semantic_similarity_cols()
    assert result._df["nearest_neighbor_paths"].to_list() == [None]


def test_add_metadata_embedding_cols_differentiates_by_extension_and_size():
    df = DataFrame(
        {
            "path": ["a.py", "b.py", "c.txt"],
            "size_bytes": [100, 100, 100_000],
            "suffix": [".py", ".py", ".txt"],
            "owner": ["alice", "alice", "bob"],
        }
    )

    result = df.add_metadata_embedding_cols()

    assert "metadata_embedding" in result.columns
    vectors = result._df["metadata_embedding"].to_list()
    assert len(vectors) == 3
    # All rows get a vector of the same length.
    assert len({len(v) for v in vectors}) == 1
    # The two .py/alice files should be identical (same categorical + size feature values).
    assert vectors[0] == vectors[1]
    # The .txt/bob/large file should differ from the .py files.
    assert vectors[2] != vectors[0]


def test_add_metadata_embedding_cols_raises_without_usable_columns():
    df = DataFrame({"path": ["a.txt", "b.txt"]})
    with pytest.raises(ValueError):
        df.add_metadata_embedding_cols()


def test_add_metadata_embedding_cols_respects_explicit_columns():
    df = DataFrame({"path": ["a.txt", "b.txt"], "depth": [1, 2], "owner": ["alice", "bob"]})
    result = df.add_metadata_embedding_cols(columns=["depth"])
    vectors = result._df["metadata_embedding"].to_list()
    # Only "depth" was requested, so the vector should be 1-dimensional (no owner one-hot).
    assert all(len(v) == 1 for v in vectors)


def test_add_metadata_embedding_cols_raises_on_unknown_explicit_column():
    df = DataFrame({"path": ["a.txt"], "depth": [1]})
    with pytest.raises(ValueError):
        df.add_metadata_embedding_cols(columns=["does_not_exist"])


def test_add_semantic_similarity_cols_blends_metadata_and_content(sample_dir):
    df = DataFrame(
        {
            "path": [
                str(sample_dir / "ml_a.txt"),
                str(sample_dir / "ml_b.md"),
                str(sample_dir / "pets.txt"),
            ],
            "suffix": [".txt", ".md", ".txt"],
        }
    )

    df = df.add_embedding_cols().add_metadata_embedding_cols(columns=["suffix"])
    result = df.add_semantic_similarity_cols(metadata_embedding_col="metadata_embedding", content_weight=0.5, top_k=2)

    rows = result._df.to_dicts()
    ml_a = next(r for r in rows if r["path"].endswith("ml_a.txt"))
    pets = next(r for r in rows if r["path"].endswith("pets.txt"))

    # ml_a.txt and pets.txt share the same extension (.txt) but different content;
    # blended similarity should differ from content-only similarity for this pair.
    content_only = df.add_semantic_similarity_cols(top_k=2)
    ml_a_content_only = next(r for r in content_only._df.to_dicts() if r["path"].endswith("ml_a.txt"))

    assert ml_a["nearest_neighbor_similarities"] != ml_a_content_only["nearest_neighbor_similarities"]
    assert pets["nearest_neighbor_paths"] is not None


def test_add_semantic_similarity_cols_raises_on_missing_metadata_column():
    df = DataFrame({"path": ["a.txt", "b.txt"], "embedding": [[1.0, 0.0], [0.0, 1.0]]})
    with pytest.raises(ValueError):
        df.add_semantic_similarity_cols(metadata_embedding_col="metadata_embedding")
