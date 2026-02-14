"""LangGraph Server entry point.

``langgraph.json`` references ``create_graph`` which is called by
``langgraph dev`` to obtain a compiled graph instance.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging

from kg_rag.agent.graph import build_agent_graph
from kg_rag.config import settings

logger = logging.getLogger(__name__)

_cached_graph = None


def _build_tools():
    """Initialize stores and build the tool list.

    Runs in a worker thread to avoid blocking the ASGI event loop.
    """
    from kg_rag.storage.nano_vector import NanoVectorStore
    from kg_rag.storage.neo4j_graph import Neo4jGraphStore
    from kg_rag.tools.vector_search import create_vector_search
    from kg_rag.tools.graph_query import create_graph_query
    from kg_rag.tools.web_search import web_search

    vector_store = NanoVectorStore()
    graph_store = Neo4jGraphStore()

    # Neo4j driver needs async init — run in a fresh event loop (we're in a
    # worker thread, so there is no running loop here).
    try:
        asyncio.run(asyncio.wait_for(graph_store.initialize(), timeout=15))
    except Exception as exc:
        logger.warning("Neo4j init failed (%s), graph_query tool will be unavailable", exc)
        return [
            create_vector_search(vector_store),
            web_search,
        ]

    return [
        create_vector_search(vector_store),
        create_graph_query(graph_store),
        web_search,
    ]


def create_graph():
    """Factory called by ``langgraph dev`` via ``langgraph.json``.

    Result is cached so subsequent calls (per-request) return instantly.
    Blocking I/O runs in a worker thread to satisfy blockbuster.
    """
    global _cached_graph
    if _cached_graph is not None:
        return _cached_graph

    logger.info("Building kg_rag graph for LangGraph Server...")
    with concurrent.futures.ThreadPoolExecutor() as pool:
        tools = pool.submit(_build_tools).result()
    compiled = build_agent_graph(tools)
    logger.info("Graph compiled successfully")
    _cached_graph = compiled
    return compiled
