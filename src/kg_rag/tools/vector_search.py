"""Vector semantic search tool for Sub-Agent use."""

from __future__ import annotations

import logging

from langchain_core.tools import BaseTool, tool

from kg_rag.config import settings
from kg_rag.storage.base import BaseVectorStore

logger = logging.getLogger(__name__)


def create_vector_search(store: BaseVectorStore) -> BaseTool:
    """Factory: create a vector_search tool bound to *store* via closure."""

    @tool
    async def vector_search(query: str) -> str:
        """Semantic similarity search over algorithm knowledge text chunks.

        Args:
            query: Natural language query describing the information needed.

        Returns:
            Formatted retrieval results with relevance scores.
        """
        try:
            results = await store.query(query, top_k=settings.top_k)
        except Exception:
            logger.exception("Vector search failed for query: %s", query)
            return "Vector search is temporarily unavailable. Please try again later."

        if not results:
            return "No relevant text chunks found."

        parts: list[str] = []
        for i, r in enumerate(results, 1):
            score = r.get("distance", 0.0)
            content = r.get("content", "")
            meta = r.get("metadata") or {}
            doc_id = meta.get("doc_id", "")
            kw_score = meta.get("keyword_score", 0) or 0
            rid = r.get("id", "")
            header = f"[{i}] (score={score:.3f}"
            if doc_id:
                header += f", doc={doc_id}"
            if kw_score:
                header += f", kw={kw_score}"
            if rid:
                header += f", id={rid[:8]}"
            header += ")"
            parts.append(f"{header}\n{content}")

        return "\n\n---\n\n".join(parts)

    return vector_search
