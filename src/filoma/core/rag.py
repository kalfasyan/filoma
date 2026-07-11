"""RAG (Retrieval-Augmented Generation) store backed by LanceDB.

Provides a ``RagStore`` class that indexes text/markdown/json/code files
from a directory tree into a local LanceDB vector store. Supports
incremental re-indexing (skips unchanged files by path+mtime) and
semantic search via embeddings.

Embedding backends (tried in order):
1. Ollama ``nomic-embed-text`` on localhost:11434
2. sentence-transformers ``all-MiniLM-L6-v2`` (optional fallback)
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any


def _resolve_embedder():
    """Resolve an embedding function, trying Ollama first then sentence-transformers.

    Returns:
        A callable ``(texts: list[str]) -> list[list[float]]``.

    """
    # 1. Try Ollama
    try:
        import requests as _req

        resp = _req.get("http://localhost:11434/", timeout=2)
        if resp.status_code == 200:

            def _ollama_embed(texts: list[str]) -> list[list[float]]:
                vectors: list[list[float]] = []
                session = _req.Session()
                for text in texts:
                    r = session.post(
                        "http://localhost:11434/api/embeddings",
                        json={"model": "nomic-embed-text", "prompt": text},
                        timeout=30,
                    )
                    r.raise_for_status()
                    data = r.json()
                    vectors.append(data["embedding"])
                return vectors

            return _ollama_embed
    except Exception:
        pass

    # 2. Fall back to sentence-transformers
    try:
        import sentence_transformers as _st

        model = _st.SentenceTransformer("all-MiniLM-L6-v2")

        def _st_embed(texts: list[str]) -> list[list[float]]:
            result = model.encode(texts, normalize_embeddings=True)
            return result.tolist()

        return _st_embed
    except ImportError:
        raise ImportError("No embedding backend available. Install one of:\n  - Ollama with nomic-embed-text model (ollama pull nomic-embed-text)\n  - pip install filoma[rag]\n") from None


_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


def _chunk_text(text: str, max_tokens: int = 512) -> list[str]:
    """Split *text* into sentence-aware chunks of at most *max_tokens* tokens.

    A rough heuristic: 1 token ≈ 0.75 words for English prose.
    """
    max_words = int(max_tokens * 0.75)
    sentences = _SENTENCE_BOUNDARY.split(text)
    chunks: list[str] = []
    current: list[str] = []
    current_word_count = 0

    for sentence in sentences:
        stripped = sentence.strip()
        if not stripped:
            continue
        words = len(stripped.split())
        if current_word_count + words > max_words and current:
            chunks.append(" ".join(current))
            current = [stripped]
            current_word_count = words
        else:
            current.append(stripped)
            current_word_count += words

    if current:
        chunks.append(" ".join(current))

    return chunks if chunks else [text.strip()[: max_tokens * 4]]


def _is_text_file(filepath: Path) -> bool:
    """Check if *filepath* is a known text format we should index."""
    suffix = filepath.suffix.lower()
    return suffix in (
        ".txt",
        ".md",
        ".markdown",
        ".rst",
        ".json",
        ".jsonl",
        ".yaml",
        ".yml",
        ".toml",
        ".ini",
        ".cfg",
        ".conf",
        ".py",
        ".rs",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".css",
        ".html",
        ".htm",
        ".xml",
        ".sql",
        ".sh",
        ".bash",
        ".zsh",
        ".fish",
        ".r",
        ".jl",
        ".go",
        ".java",
        ".c",
        ".cpp",
        ".h",
        ".hpp",
        ".rb",
        ".php",
        ".swift",
        ".kt",
        ".scala",
        ".lua",
        ".pl",
        ".pm",
        ".tf",
        ".tfvars",
        ".env",
        ".make",
        ".cmake",
        ".gradle",
        ".cs",
    )


class RagStore:
    """LanceDB-backed retrieval store for a directory tree.

    Indexes text files, chunks them at sentence boundaries, embeds with
    a configurable backend, and persists vectors for fast semantic search.

    Parameters
    ----------
        db_path: Filesystem path for the LanceDB database directory.

    """

    def __init__(self, db_path: str) -> None:
        """Initialize the RAG store.

        Args:
            db_path: Filesystem path for the LanceDB database directory.

        """
        import lancedb

        self._db_path = str(db_path)
        self._db = lancedb.connect(self._db_path)
        self._embedder = _resolve_embedder()
        self._table_name = "filoma_chunks"

    def index(self, directory: str, pattern: str = "*") -> int:
        """Walk *directory*, chunk text files, embed, and upsert into LanceDB.

        Files whose ``(path, mtime)`` pair has not changed are skipped
        (incremental re-index). Returns the total number of chunks
        currently stored after the index pass (new + unchanged).

        Args:
            directory: Root directory to scan for text files.
            pattern: Glob pattern to filter files within the directory.
                     Defaults to ``*`` (all files). Only text files
                     matching the pattern are indexed.

        """
        dir_path = Path(directory).resolve()
        if not dir_path.exists():
            raise FileNotFoundError(f"Directory not found: {directory}")

        # 1. Scan filesystem
        current_files: dict[str, str] = {}
        files_to_index: list[Path] = []

        for filepath in dir_path.rglob(pattern):
            if not filepath.is_file():
                continue
            if not _is_text_file(filepath):
                continue
            rel = str(filepath.relative_to(dir_path))
            try:
                mtime = str(os.path.getmtime(filepath))
            except OSError:
                continue
            current_files[rel] = mtime
            files_to_index.append(filepath)

        # 2. Load existing table (if any) to compute delta
        existing_paths: set[str] = set()
        try:
            table = self._db.open_table(self._table_name)
            rows = table.search().limit(0).to_arrow()  # type: ignore[union-attr]
            del rows
            existing = table.to_pandas()
            existing["_lookup"] = existing["path"] + "::" + existing["mtime"].astype(str)
            existing_paths = set(existing["_lookup"].tolist())
        except Exception:
            existing = None

        # 3. Process new or changed files
        new_chunks: list[dict[str, Any]] = []
        skipped = 0

        for filepath in files_to_index:
            rel = str(filepath.relative_to(dir_path))
            mtime = current_files[rel]
            lookup = f"{rel}::{mtime}"
            if lookup in existing_paths:
                skipped += 1
                continue

            try:
                content = filepath.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            chunks = _chunk_text(content)
            if not chunks:
                continue

            embeddings = self._embedder(chunks)

            for idx, (chunk_text, vec) in enumerate(zip(chunks, embeddings)):
                new_chunks.append(
                    {
                        "path": rel,
                        "chunk_idx": idx,
                        "text": chunk_text,
                        "vector": vec,
                        "mtime": mtime,
                    }
                )

        # 4. Upsert to LanceDB
        final_count = 0
        if new_chunks or existing is not None:
            if new_chunks:
                import pyarrow as pa

                new_table = pa.table(
                    {
                        "path": pa.array([c["path"] for c in new_chunks], type=pa.string()),
                        "chunk_idx": pa.array([c["chunk_idx"] for c in new_chunks], type=pa.int64()),
                        "text": pa.array([c["text"] for c in new_chunks], type=pa.string()),
                        "vector": pa.array([c["vector"] for c in new_chunks], type=pa.list_(pa.float64())),
                        "mtime": pa.array([c["mtime"] for c in new_chunks], type=pa.string()),
                    }
                )

                if existing is None:
                    self._db.create_table(self._table_name, new_table)
                else:
                    table = self._db.open_table(self._table_name)
                    table.delete("1 = 1")  # type: ignore[union-attr]
                    rematerialized = pa.concat_tables([existing, new_table])  # type: ignore[union-attr]
                    self._db.drop_table(self._table_name)
                    self._db.create_table(self._table_name, rematerialized)

            final_count = new_chunks[-1]["chunk_idx"] + 1 if new_chunks else 0

        return final_count

    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Semantic search over indexed chunks.

        Args:
            query: Natural language query string.
            top_k: Number of top results to return.

        Returns:
            List of result dicts with keys: ``path``, ``chunk_idx``,
            ``text``, ``_distance``.

        """
        query_vec = self._embedder([query])[0]

        try:
            table = self._db.open_table(self._table_name)
        except Exception:
            return []

        results = table.search(query_vec).limit(top_k).to_list()  # type: ignore[union-attr]

        return [
            {
                "path": r["path"],
                "chunk_idx": r["chunk_idx"],
                "text": r["text"],
                "_distance": r["_distance"],
            }
            for r in results
        ]

    def close(self) -> None:
        """Close the underlying LanceDB connection."""
        pass
