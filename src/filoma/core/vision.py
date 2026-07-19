"""Image embedding backends for filoma.

Provides fast, CPU-friendly vision embeddings for image files by reusing
sentence-transformers' bundled CLIP support — already a core filoma
dependency (see ``pyproject.toml``), so no extra install is required to
turn image content into a numeric fingerprint suitable for similarity
search or clustering.

Model choices (short name -> underlying sentence-transformers model id),
in increasing order of size/accuracy and decreasing speed:

- ``"clip-vit-b32"`` (default): OpenAI CLIP ViT-B/32. The fastest option —
  32px patches mean far fewer tokens per image than B/16 or L/14 — while
  still producing a 512-dim vector that captures overall visual semantics
  (subject, scene, composition), not just raw pixel similarity. Good
  default for "fast similarity matrix over a folder of images".
- ``"clip-vit-b16"``: CLIP ViT-B/16. Finer 16px patches and sharper
  features, at roughly 3-4x the compute of B/32.
- ``"clip-vit-l14"``: CLIP ViT-L/14. Largest and slowest, most accurate.

All three embed images into the same kind of general-purpose CLIP visual
space, directly usable with cosine similarity — e.g. via
``DataFrame.add_semantic_similarity_cols(embedding_col="image_embedding")``.

GPU usage: by default (``device=None``), sentence-transformers auto-selects
the fastest available torch device — CUDA, then Apple Silicon MPS, then
CPU — so a GPU is used automatically whenever one is available; nothing
extra to configure. Pass an explicit ``device`` (e.g. ``"cpu"``, ``"cuda"``,
``"cuda:1"``, ``"mps"``) to override that choice.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

IMAGE_MODEL_ALIASES: Dict[str, str] = {
    "clip-vit-b32": "clip-ViT-B-32",
    "clip-vit-b16": "clip-ViT-B-16",
    "clip-vit-l14": "clip-ViT-L-14",
}

DEFAULT_IMAGE_MODEL = "clip-vit-b32"

# Loaded CLIP models are cached per-process (by resolved model id + device)
# since loading weights is the slow part of embedding — an interactive
# session (filoma ask/chat, or a long-lived MCP server) should pay that
# cost once.
_MODEL_CACHE: Dict[Tuple[str, Optional[str]], Callable[[List[Any]], List[List[float]]]] = {}


def resolve_image_model_name(model: str) -> str:
    """Resolve a short model alias (e.g. ``"clip-vit-b32"``) to its full sentence-transformers model id.

    Unknown names are passed through unchanged, so any sentence-transformers
    image model id (e.g. a custom fine-tuned CLIP checkpoint) can also be
    used directly.
    """
    return IMAGE_MODEL_ALIASES.get(model.lower(), model)


def _resolve_image_embedder(model: str = DEFAULT_IMAGE_MODEL, device: Optional[str] = None) -> Callable[[List[Any]], List[List[float]]]:
    """Return a callable that embeds a list of PIL Images using *model*.

    Args:
        model: Short alias (see ``IMAGE_MODEL_ALIASES``) or any
            sentence-transformers image model id. Defaults to the fastest
            option, ``"clip-vit-b32"``.
        device: Torch device to run on, e.g. ``"cpu"``, ``"cuda"``,
            ``"cuda:1"``, ``"mps"``. If None (default), sentence-transformers
            auto-selects the fastest available device — CUDA, then MPS,
            then CPU.

    Returns:
        A callable ``(images: list[PIL.Image.Image]) -> list[list[float]]``
        that returns L2-normalized embedding vectors, one per input image.
        The callable has a ``.device`` attribute (str) reporting which
        device the underlying model actually loaded onto — useful for
        reporting back to the user whether a GPU was used.

    Raises:
        ImportError: If sentence-transformers is not installed.
        ValueError: If the model name fails to load.

    """
    resolved_name = resolve_image_model_name(model)
    cache_key = (resolved_name, device)

    if cache_key in _MODEL_CACHE:
        return _MODEL_CACHE[cache_key]

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        raise ImportError("Image embedding requires sentence-transformers. Install with 'pip install filoma[rag]'.") from None

    try:
        st_model = SentenceTransformer(resolved_name, device=device)
    except Exception as e:
        known = ", ".join(sorted(IMAGE_MODEL_ALIASES))
        raise ValueError(f"Could not load image embedding model '{model}' (resolved to '{resolved_name}'). Known short names: {known}. Details: {e}") from e

    def _embed(images: List[Any]) -> List[List[float]]:
        result = st_model.encode(images, normalize_embeddings=True, convert_to_numpy=True)
        return result.tolist()

    _embed.device = str(st_model.device)  # type: ignore[attr-defined]

    _MODEL_CACHE[cache_key] = _embed
    return _embed
