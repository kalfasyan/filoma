"""Tests for DataFrame.add_image_embedding_cols.

Uses a deterministic fake image embedder (monkeypatched onto
``filoma.core.vision``) so these tests don't require sentence-transformers
to download real CLIP weights.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest
from PIL import Image

from filoma.dataframe import DataFrame


def _fake_image_embed(images):
    """Deterministic embedding: vector of each image's average RGB channel means."""
    vectors = []
    for img in images:
        pixels = list(img.getdata())
        n = len(pixels)
        r = sum(p[0] for p in pixels) / n
        g = sum(p[1] for p in pixels) / n
        b = sum(p[2] for p in pixels) / n
        vectors.append([r, g, b])
    return vectors


@pytest.fixture(autouse=True)
def patch_image_embedder(monkeypatch):
    monkeypatch.setattr("filoma.core.vision._resolve_image_embedder", lambda model="clip-vit-b32", device=None: _fake_image_embed)


@pytest.fixture
def sample_dir(tmp_path):
    Image.new("RGB", (4, 4), color=(255, 0, 0)).save(tmp_path / "red.png")
    Image.new("RGB", (4, 4), color=(250, 5, 5)).save(tmp_path / "red_ish.png")
    Image.new("RGB", (4, 4), color=(0, 0, 255)).save(tmp_path / "blue.jpg")
    (tmp_path / "notes.txt").write_text("just some text, not an image")
    return tmp_path


def test_add_image_embedding_cols_adds_vectors_for_images(sample_dir):
    df = DataFrame(
        {
            "path": [
                str(sample_dir / "red.png"),
                str(sample_dir / "blue.jpg"),
                str(sample_dir / "notes.txt"),
            ]
        }
    )

    result = df.add_image_embedding_cols()

    assert "image_embedding" in result.columns
    embeddings = result._df["image_embedding"].to_list()
    assert embeddings[0] is not None and len(embeddings[0]) == 3
    assert embeddings[1] is not None
    # Non-image file is skipped.
    assert embeddings[2] is None


def test_add_image_embedding_cols_raises_on_missing_column():
    df = DataFrame({"other": ["a.png", "b.png"]})
    with pytest.raises(ValueError):
        df.add_image_embedding_cols()


def test_add_image_embedding_cols_accepts_model_argument(sample_dir):
    df = DataFrame({"path": [str(sample_dir / "red.png")]})
    result = df.add_image_embedding_cols(model="clip-vit-l14")
    assert result._df["image_embedding"].to_list()[0] is not None


def test_add_image_embedding_cols_passes_device_through(monkeypatch, sample_dir):
    """The `device` argument must reach `_resolve_image_embedder` unchanged."""
    seen = {}

    def _fake_resolver(model="clip-vit-b32", device=None):
        seen["model"] = model
        seen["device"] = device
        return _fake_image_embed

    monkeypatch.setattr("filoma.core.vision._resolve_image_embedder", _fake_resolver)

    df = DataFrame({"path": [str(sample_dir / "red.png")]})
    result = df.add_image_embedding_cols(device="cpu")

    assert seen["device"] == "cpu"
    # The resolved device (or requested one, when the embedder doesn't report
    # one back) is recorded in lineage for traceability.
    assert result.lineage[-1]["parameters"]["device"] == "cpu"


def test_add_semantic_similarity_cols_finds_similar_images(sample_dir):
    df = DataFrame(
        {
            "path": [
                str(sample_dir / "red.png"),
                str(sample_dir / "red_ish.png"),
                str(sample_dir / "blue.jpg"),
            ]
        }
    )

    result = df.add_image_embedding_cols().add_semantic_similarity_cols(embedding_col="image_embedding", top_k=1)

    assert "nearest_neighbor_paths" in result.columns
    rows = result._df.to_dicts()
    red = next(r for r in rows if r["path"].endswith("/red.png"))

    # The two near-identical reds should be each other's nearest neighbor,
    # not the unrelated blue image.
    assert red["nearest_neighbor_paths"][0].endswith("red_ish.png")
