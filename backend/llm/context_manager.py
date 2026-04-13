"""
GORVAX GAME FACTORY — Smart Context Window Manager (Roadmap v3 Item #4)

Selects context by semantic relevance instead of brute-force truncation.
Uses VectorStore (ChromaDB) embeddings when available, falls back to
a lightweight TF-IDF keyword similarity approach.

Impact: ~20% fewer tokens per LLM call.
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from backend.memory.vector_store import VectorStore

logger = logging.getLogger(__name__)

# ── Constants ───────────────────────────────────────────
DEFAULT_MAX_CONTEXT_CHARS = 6000
DEFAULT_TOP_K = 5
_STOP_WORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "must",
    "in", "on", "at", "to", "for", "of", "with", "by", "from", "as",
    "into", "through", "during", "before", "after", "above", "below",
    "and", "but", "or", "nor", "not", "so", "yet", "both", "either",
    "neither", "each", "every", "all", "any", "few", "more", "most",
    "other", "some", "such", "no", "only", "own", "same", "than",
    "too", "very", "just", "because", "if", "when", "while", "this",
    "that", "these", "those", "it", "its", "i", "we", "you", "he",
    "she", "they", "me", "him", "her", "us", "them", "my", "your",
    "his", "our", "their", "what", "which", "who", "whom",
    "de", "da", "do", "das", "dos", "em", "no", "na", "nos", "nas",
    "um", "uma", "uns", "umas", "e", "ou", "que", "se", "com", "para",
})

_WORD_SPLIT = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*")


@dataclass
class ContextChunk:
    """A piece of context with metadata."""
    key: str            # identifier (filename, history entry, etc.)
    content: str        # the text content
    relevance: float = 0.0  # computed relevance score (0-1)
    char_count: int = 0

    def __post_init__(self) -> None:
        if not self.char_count:
            self.char_count = len(self.content)


@dataclass
class ContextStats:
    """Stats from a context selection operation."""
    total_chunks: int = 0
    selected_chunks: int = 0
    total_chars_before: int = 0
    total_chars_after: int = 0
    compression_ratio: float = 0.0


class ContextManager:
    """
    Smart Context Window Manager.

    Selects the most relevant pieces of context for an LLM call,
    based on semantic similarity to the task. Uses VectorStore
    for embeddings when available, otherwise falls back to
    TF-IDF keyword similarity.

    Usage:
        cm = ContextManager()
        selected = cm.select_context(
            task_description="Fix the combat damage calculation",
            available_context={"combat.js": "...", "ui.js": "..."},
            top_k=3,
        )
    """

    def __init__(
        self,
        vector_store: VectorStore | None = None,
        max_context_chars: int = DEFAULT_MAX_CONTEXT_CHARS,
    ) -> None:
        self._vector_store = vector_store
        self._max_context_chars = max_context_chars
        self._embedding_cache: dict[str, str] = {}  # content_hash → doc_id
        self._stats = ContextStats()

    @property
    def has_vector_store(self) -> bool:
        """Whether a functional VectorStore is available."""
        if self._vector_store is None:
            return False
        return (
            hasattr(self._vector_store, "is_available")
            and self._vector_store.is_available
        )

    # ── Main API ─────────────────────────────────────────

    def select_context(
        self,
        task_description: str,
        available_context: dict[str, str],
        top_k: int = DEFAULT_TOP_K,
        max_chars: int | None = None,
    ) -> dict[str, str]:
        """
        Select the top-K most relevant context items for the task.

        Args:
            task_description: What the agent is trying to do.
            available_context: Map of key → text content.
            top_k: Number of items to select.
            max_chars: Override max total chars (default: self._max_context_chars).

        Returns:
            Filtered context dict with only the most relevant items,
            fitting within the character budget.
        """
        if not available_context:
            return {}

        budget = max_chars or self._max_context_chars
        chunks = [
            ContextChunk(key=k, content=v)
            for k, v in available_context.items()
            if v.strip()
        ]

        if not chunks:
            return {}

        # If we have fewer chunks than top_k, keep all
        if len(chunks) <= top_k:
            ranked = chunks
        else:
            ranked = self._rank_chunks(task_description, chunks)[:top_k]

        # Fit within character budget
        result: dict[str, str] = {}
        chars_used = 0
        total_before = sum(c.char_count for c in chunks)

        for chunk in ranked:
            remaining = budget - chars_used
            if remaining <= 0:
                break
            if chunk.char_count <= remaining:
                result[chunk.key] = chunk.content
                chars_used += chunk.char_count
            else:
                # Truncate last chunk to fit
                result[chunk.key] = chunk.content[:remaining] + "\n...[context truncated]"
                chars_used += remaining

        total_after = sum(len(v) for v in result.values())
        self._stats = ContextStats(
            total_chunks=len(chunks),
            selected_chunks=len(result),
            total_chars_before=total_before,
            total_chars_after=total_after,
            compression_ratio=round(
                1.0 - (total_after / total_before), 3
            ) if total_before > 0 else 0.0,
        )

        if self._stats.compression_ratio > 0:
            logger.debug(
                "📦 ContextManager: %d/%d chunks, %d→%d chars (%.0f%% reduced)",
                self._stats.selected_chunks,
                self._stats.total_chunks,
                self._stats.total_chars_before,
                self._stats.total_chars_after,
                self._stats.compression_ratio * 100,
            )

        return result

    def compress_with_relevance(
        self,
        task_description: str,
        files: dict[str, str],
        history: list[Any] | None = None,
        max_chars: int | None = None,
    ) -> dict[str, str]:
        """
        Compress context using relevance-based selection.

        Combines files and history into a single pool, ranks by relevance,
        and returns within the character budget.

        Args:
            task_description: What the agent is working on.
            files: Map of filename → source code.
            history: Optional history entries (converted to strings).
            max_chars: Override character budget.

        Returns:
            Filtered and compressed context dict.
        """
        combined: dict[str, str] = {}
        for k, v in files.items():
            combined[f"file:{k}"] = v

        if history:
            for i, entry in enumerate(history):
                text = str(entry) if not isinstance(entry, str) else entry
                if text.strip():
                    combined[f"history:{i}"] = text

        return self.select_context(
            task_description=task_description,
            available_context=combined,
            max_chars=max_chars,
        )

    # ── Ranking ──────────────────────────────────────────

    def _rank_chunks(
        self,
        task: str,
        chunks: list[ContextChunk],
    ) -> list[ContextChunk]:
        """
        Rank chunks by relevance to the task.

        Uses VectorStore for semantic similarity if available,
        otherwise falls back to TF-IDF keyword similarity.
        """
        if self.has_vector_store:
            return self._rank_by_vector(task, chunks)
        return self._rank_by_keywords(task, chunks)

    def _rank_by_vector(
        self,
        task: str,
        chunks: list[ContextChunk],
    ) -> list[ContextChunk]:
        """Rank using VectorStore semantic search."""
        assert self._vector_store is not None

        collection = "context_ranking"

        # Store chunks temporarily for ranking
        stored_ids: list[str] = []
        chunk_map: dict[str, ContextChunk] = {}

        try:
            for chunk in chunks:
                content_hash = hashlib.md5(
                    chunk.content[:500].encode("utf-8")
                ).hexdigest()[:10]
                doc_id = f"ctx_{content_hash}"
                chunk_map[doc_id] = chunk
                stored_ids.append(doc_id)

                # Only store if not cached
                if content_hash not in self._embedding_cache:
                    self._vector_store.store(
                        collection=collection,
                        text=chunk.content[:1000],  # limit for embedding
                        metadata={"key": chunk.key},
                        doc_id=doc_id,
                    )
                    self._embedding_cache[content_hash] = doc_id

            # Query for most relevant
            results = self._vector_store.query(
                collection=collection,
                text=task[:500],
                top_k=len(chunks),
            )

            ranked: list[ContextChunk] = []
            seen: set[str] = set()
            for result in results:
                doc_id = result.get("id", "")
                if doc_id in chunk_map and doc_id not in seen:
                    c = chunk_map[doc_id]
                    distance = result.get("distance", 1.0)
                    c.relevance = max(0.0, 1.0 - distance)
                    ranked.append(c)
                    seen.add(doc_id)

            # Append any chunks not returned by vector search
            for chunk in chunks:
                cid = f"ctx_{hashlib.md5(chunk.content[:500].encode('utf-8')).hexdigest()[:10]}"
                if cid not in seen:
                    chunk.relevance = 0.0
                    ranked.append(chunk)

            return ranked

        except Exception as exc:
            logger.debug("VectorStore ranking failed, falling back to keywords: %s", exc)
            return self._rank_by_keywords(task, chunks)

    def _rank_by_keywords(
        self,
        task: str,
        chunks: list[ContextChunk],
    ) -> list[ContextChunk]:
        """
        Rank by TF-IDF-inspired keyword similarity.

        Extracts keywords from the task and scores each chunk by
        the number of matching keywords, weighted by inverse document
        frequency across all chunks.
        """
        task_tokens = self._tokenize(task)
        if not task_tokens:
            return chunks

        # Compute document frequency (DF) for each token
        all_docs_tokens = [self._tokenize(c.content) for c in chunks]
        doc_count = len(chunks)
        df: Counter[str] = Counter()
        for doc_tokens in all_docs_tokens:
            for token in set(doc_tokens):
                df[token] += 1

        # Score each chunk
        for i, chunk in enumerate(chunks):
            doc_tokens = all_docs_tokens[i]
            if not doc_tokens:
                chunk.relevance = 0.0
                continue

            doc_tf: Counter[str] = Counter(doc_tokens)
            score = 0.0
            for token in task_tokens:
                tf = doc_tf.get(token, 0)
                if tf > 0:
                    idf = math.log((doc_count + 1) / (df.get(token, 0) + 1)) + 1
                    score += tf * idf

            # Normalize by document length to avoid bias toward long docs
            chunk.relevance = score / (len(doc_tokens) ** 0.5) if doc_tokens else 0.0

        # Sort by relevance descending
        return sorted(chunks, key=lambda c: c.relevance, reverse=True)

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Extract lowercase tokens, excluding stop words."""
        tokens = _WORD_SPLIT.findall(text.lower())
        return [t for t in tokens if t not in _STOP_WORDS and len(t) > 1]

    # ── Stats ────────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        """Return statistics from the last context selection."""
        return {
            "total_chunks": self._stats.total_chunks,
            "selected_chunks": self._stats.selected_chunks,
            "total_chars_before": self._stats.total_chars_before,
            "total_chars_after": self._stats.total_chars_after,
            "compression_ratio": self._stats.compression_ratio,
            "has_vector_store": self.has_vector_store,
        }
