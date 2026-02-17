"""Web search tool — uses Firecrawl for supplementary knowledge retrieval."""

from __future__ import annotations

import logging

from langchain_core.tools import tool

from kg_rag.config import settings

logger = logging.getLogger(__name__)

_client: "AsyncFirecrawl | None" = None  # noqa: F821


def _get_client() -> "AsyncFirecrawl":  # noqa: F821
    from firecrawl import AsyncFirecrawl

    global _client
    if _client is None:
        _client = AsyncFirecrawl(api_key=settings.firecrawl_api_key)
    return _client


@tool
async def web_search(query: str) -> str:
    """Search the web for supplementary algorithm knowledge.

    Used when local knowledge graph and vector store lack sufficient
    information to answer the user's question.

    Args:
        query: Search query string.

    Returns:
        Formatted search results or an error message.
    """
    if not settings.firecrawl_api_key:
        return "Web search is not configured (missing FIRECRAWL_API_KEY)."

    client = _get_client()

    try:
        results = await client.search(query, limit=5)
    except Exception as e:
        logger.warning("Firecrawl search failed: %s", e)
        return "Web search failed. Please try again later."

    items = results.web or []
    if not items:
        return "No web results found."

    parts: list[str] = []
    for i, item in enumerate(items, 1):
        title = getattr(item, "title", "") or ""
        url = getattr(item, "url", "") or ""
        snippet = getattr(item, "description", "") or ""
        if not snippet and hasattr(item, "markdown"):
            snippet = (getattr(item, "markdown", "") or "")[:300]
        parts.append(f"[{i}] {title}\n    {url}\n    {snippet}")

    return "\n\n".join(parts)
