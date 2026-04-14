"""
GORVAX GAME FACTORY — Vector Store
ChromaDB-backed vector storage for semantic search over
code chunks, GDD versions, decisions, and failures.
Graceful fallback when ChromaDB is not installed.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from backend.config import STORAGE_DIR

logger = logging.getLogger(__name__)

# ── Graceful import ────────────────────────────────────
_CHROMADB_AVAILABLE = False
try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings
    _CHROMADB_AVAILABLE = True
except ImportError:
    logger.warning(
        "chromadb not installed — VectorStore will run in no-op mode. "
        "Install with: pip install chromadb sentence-transformers"
    )

# Default collection names
COLLECTIONS = ("code_chunks", "gdd_versions", "decisions", "failures")


class VectorStore:
    """
    ChromaDB-backed vector store with local embeddings.

    Collections:
    - code_chunks: Indexed code snippets
    - gdd_versions: GDD versions
    - decisions: Agent decisions
    - failures: Failures and their resolutions

    If ChromaDB is not installed, operates in no-op mode
    (all queries return empty lists).

    Uses sentence-transformers/all-MiniLM-L6-v2 for local embeddings.
    """

    def __init__(
        self,
        persist_dir: Path | None = None,
        embedding_model: str = "all-MiniLM-L6-v2",
    ) -> None:
        self._persist_dir = persist_dir or (STORAGE_DIR / "chromadb")
        self._embedding_model = embedding_model
        self._client: Any = None
        self._collections: dict[str, Any] = {}
        self._available = _CHROMADB_AVAILABLE

        if self._available:
            self._init_chromadb()

    def _init_chromadb(self) -> None:
        """Initialize the ChromaDB client with local persistence."""
        try:
            self._persist_dir.mkdir(parents=True, exist_ok=True)

            self._client = chromadb.PersistentClient(
                path=str(self._persist_dir),
            )

            # Try SentenceTransformer, fallback to default
            embedding_fn = None
            try:
                from chromadb.utils.embedding_functions import (
                    SentenceTransformerEmbeddingFunction,
                )
                embedding_fn = SentenceTransformerEmbeddingFunction(
                    model_name=self._embedding_model
                )
            except ImportError:
                logger.warning(
                    "sentence-transformers not installed, "
                    "using ChromaDB default embeddings"
                )

            # Create/get collections
            for name in COLLECTIONS:
                kwargs: dict[str, Any] = {"name": name}
                if embedding_fn is not None:
                    kwargs["embedding_function"] = embedding_fn
                self._collections[name] = (
                    self._client.get_or_create_collection(**kwargs)
                )

            logger.info(
                "✅ VectorStore initialized at %s (%d collections)",
                self._persist_dir,
                len(self._collections),
            )

        except Exception as exc:
            logger.error("Failed to initialize ChromaDB: %s", exc)
            self._available = False

    # ── API Pública ────────────────────────────────────

    @property
    def is_available(self) -> bool:
        """Whether ChromaDB is operational."""
        return self._available

    def store(
        self,
        collection: str,
        text: str,
        metadata: dict[str, Any] | None = None,
        doc_id: str | None = None,
    ) -> str | None:
        """
        Store a document in the collection.

        Args:
            collection: Collection name
            text: Text to store
            metadata: Associated metadata
            doc_id: Optional ID (auto-generated if omitted)

        Returns:
            Stored document ID or None in no-op mode
        """
        if not self._available:
            return None

        coll = self._collections.get(collection)
        if coll is None:
            logger.warning("Unknown collection: %s", collection)
            return None

        if doc_id is None:
            import hashlib
            doc_id = hashlib.sha256(
                f"{collection}:{text[:200]}".encode()
            ).hexdigest()[:16]

        try:
            coll.add(
                documents=[text],
                metadatas=[metadata or {}],
                ids=[doc_id],
            )
            return doc_id

        except Exception as exc:
            logger.warning("Error storing in %s: %s", collection, exc)
            return None

    def query(
        self,
        collection: str,
        text: str,
        top_k: int = 5,
        where: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Search for the most similar documents to the text.

        Args:
            collection: Collection name
            text: Search text
            top_k: Number of results
            where: Optional metadata filter

        Returns:
            List of dicts with 'id', 'document', 'metadata', 'distance'
        """
        if not self._available:
            return []

        coll = self._collections.get(collection)
        if coll is None:
            return []

        # Validate text input — ChromaDB requires a non-empty string
        if not isinstance(text, str) or not text.strip():
            logger.debug("Skipping query in %s: text is empty or non-string", collection)
            return []

        try:
            kwargs: dict[str, Any] = {
                "query_texts": [text],
                "n_results": top_k,
            }
            if where:
                kwargs["where"] = where

            results = coll.query(**kwargs)

            output: list[dict[str, Any]] = []
            if results and results.get("documents"):
                docs = results["documents"][0]
                ids = results["ids"][0] if results.get("ids") else [""] * len(docs)
                metas = (
                    results["metadatas"][0]
                    if results.get("metadatas")
                    else [{}] * len(docs)
                )
                dists = (
                    results["distances"][0]
                    if results.get("distances")
                    else [0.0] * len(docs)
                )

                for i, doc in enumerate(docs):
                    output.append({
                        "id": ids[i],
                        "document": doc,
                        "metadata": metas[i],
                        "distance": dists[i],
                    })

            return output

        except Exception as exc:
            logger.warning("Query error in %s: %s", collection, exc)
            return []

    def delete(self, collection: str, doc_id: str) -> bool:
        """
        Remove a document from the collection.

        Args:
            collection: Collection name
            doc_id: Document ID

        Returns:
            True if successfully removed
        """
        if not self._available:
            return False

        coll = self._collections.get(collection)
        if coll is None:
            return False

        try:
            coll.delete(ids=[doc_id])
            return True
        except Exception as exc:
            logger.warning("Error deleting from %s: %s", collection, exc)
            return False

    def count(self, collection: str) -> int:
        """Count documents in a collection."""
        if not self._available:
            return 0

        coll = self._collections.get(collection)
        if coll is None:
            return 0

        try:
            return coll.count()
        except Exception:
            return 0

    def get_stats(self) -> dict[str, Any]:
        """Store statistics."""
        stats: dict[str, Any] = {
            "available": self._available,
            "persist_dir": str(self._persist_dir),
        }
        if self._available:
            stats["collections"] = {
                name: self.count(name) for name in COLLECTIONS
            }
        return stats
