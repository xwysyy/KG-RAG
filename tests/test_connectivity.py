"""Connectivity smoke tests — verify LLM API and Neo4j are reachable.

Run with:  pytest tests/test_connectivity.py -m integration
"""

from __future__ import annotations

import pytest

from kg_rag.config import settings

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_neo4j_connection():
    """Neo4j should accept auth and execute a trivial query."""
    if not settings.neo4j_uri or not settings.neo4j_password:
        pytest.skip("NEO4J_URI or NEO4J_PASSWORD not set")
    from neo4j import AsyncGraphDatabase

    driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_username, settings.neo4j_password),
    )
    try:
        async with driver.session(database=settings.neo4j_database) as session:
            result = await session.run("RETURN 1 AS n")
            record = await result.single()
            assert record["n"] == 1
    finally:
        await driver.close()


@pytest.mark.asyncio
async def test_llm_api_chat():
    """LLM endpoint should respond to a minimal chat completion."""
    if not settings.llm_api_key:
        pytest.skip("LLM_API_KEY not set")
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import HumanMessage

    llm = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        temperature=0,
        max_tokens=16,
    )
    resp = await llm.ainvoke([HumanMessage(content="Say OK")])
    assert len(resp.content) > 0


@pytest.mark.asyncio
async def test_embedding_api():
    """Embedding endpoint should return a vector of the configured dimension."""
    if not settings.embedding_api_key or not settings.embedding_base_url:
        pytest.skip("EMBEDDING_API_KEY or EMBEDDING_BASE_URL not set")
    from langchain_openai import OpenAIEmbeddings

    emb = OpenAIEmbeddings(
        model=settings.embedding_model,
        openai_api_key=settings.embedding_api_key,
        openai_api_base=settings.embedding_base_url,
    )
    vectors = await emb.aembed_documents(["hello world"])
    assert len(vectors) == 1
    assert len(vectors[0]) == settings.embedding_dim
