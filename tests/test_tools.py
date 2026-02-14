"""Tests for kg_rag.tools — web_search, vector_search, graph_query."""

import pytest
from unittest.mock import AsyncMock, patch

from firecrawl.types import SearchData, SearchResultWeb


# ---- web_search ----

class TestWebSearch:
    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        from kg_rag.tools.web_search import web_search

        with patch("kg_rag.tools.web_search.settings") as mock_settings:
            mock_settings.firecrawl_api_key = ""
            result = await web_search.ainvoke({"query": "BFS algorithm"})
            assert "not configured" in result

    @pytest.mark.asyncio
    async def test_successful_search(self):
        from kg_rag.tools.web_search import web_search

        mock_client = AsyncMock()
        mock_client.search.return_value = SearchData(
            web=[SearchResultWeb(url="https://example.com", title="BFS Guide", description="A guide to BFS")],
        )

        with (
            patch("kg_rag.tools.web_search.settings") as mock_settings,
            patch("firecrawl.AsyncFirecrawl", return_value=mock_client),
        ):
            mock_settings.firecrawl_api_key = "fc-test"
            result = await web_search.ainvoke({"query": "BFS"})
            assert "BFS Guide" in result
            assert "https://example.com" in result

    @pytest.mark.asyncio
    async def test_empty_results(self):
        from kg_rag.tools.web_search import web_search

        mock_client = AsyncMock()
        mock_client.search.return_value = SearchData(web=[])

        with (
            patch("kg_rag.tools.web_search.settings") as mock_settings,
            patch("firecrawl.AsyncFirecrawl", return_value=mock_client),
        ):
            mock_settings.firecrawl_api_key = "fc-test"
            result = await web_search.ainvoke({"query": "nonexistent"})
            assert "No web results" in result

    @pytest.mark.asyncio
    async def test_api_error(self):
        from kg_rag.tools.web_search import web_search

        mock_client = AsyncMock()
        mock_client.search.side_effect = RuntimeError("API down")

        with (
            patch("kg_rag.tools.web_search.settings") as mock_settings,
            patch("firecrawl.AsyncFirecrawl", return_value=mock_client),
        ):
            mock_settings.firecrawl_api_key = "fc-test"
            result = await web_search.ainvoke({"query": "BFS"})
            assert "failed" in result.lower()
            assert "API down" not in result  # internal details must not leak


# ---- vector_search ----

class TestVectorSearch:
    @pytest.mark.asyncio
    async def test_empty_results(self):
        from kg_rag.tools.vector_search import create_vector_search

        mock_store = AsyncMock()
        mock_store.query.return_value = []

        with patch("kg_rag.tools.vector_search.settings") as mock_settings:
            mock_settings.top_k = 2
            tool = create_vector_search(mock_store)
            result = await tool.ainvoke({"query": "BFS"})

        mock_store.query.assert_awaited_once_with("BFS", top_k=2)
        assert "No relevant text chunks found." == result

    @pytest.mark.asyncio
    async def test_formats_results(self):
        from kg_rag.tools.vector_search import create_vector_search

        mock_store = AsyncMock()
        mock_store.query.return_value = [
            {"distance": 0.1234, "content": "BFS is a graph traversal algorithm."},
        ]

        with patch("kg_rag.tools.vector_search.settings") as mock_settings:
            mock_settings.top_k = 1
            tool = create_vector_search(mock_store)
            result = await tool.ainvoke({"query": "BFS"})

        mock_store.query.assert_awaited_once_with("BFS", top_k=1)
        assert "[1]" in result
        assert "score=0.123" in result
        assert "graph traversal" in result


# ---- graph_query ----

class TestGraphQuery:
    class _DummyLLM:
        def __init__(self, content: str):
            self._content = content

        async def ainvoke(self, _prompt):
            from types import SimpleNamespace

            return SimpleNamespace(content=self._content)

    @pytest.mark.asyncio
    async def test_strips_code_fences_and_formats_records(self):
        from kg_rag.tools.graph_query import create_graph_query

        mock_graph = AsyncMock()
        mock_graph.query_cypher.return_value = [{"name": "BFS", "type": "Algorithm"}]

        dummy_llm = self._DummyLLM(
            "```cypher\nMATCH (e:Entity) RETURN e.name AS name, e.type AS type LIMIT 1\n```"
        )

        with patch("kg_rag.tools.graph_query.ChatOpenAI", return_value=dummy_llm):
            tool = create_graph_query(mock_graph)
            result = await tool.ainvoke({"question": "Give me one entity"})

        called_cypher = mock_graph.query_cypher.call_args.args[0]
        assert "```" not in called_cypher
        assert "MATCH" in called_cypher
        assert "[1]" in result
        assert "name: BFS" in result
        assert "type: Algorithm" in result

    @pytest.mark.asyncio
    async def test_strips_leading_language_tag_line(self):
        from kg_rag.tools.graph_query import create_graph_query

        mock_graph = AsyncMock()
        mock_graph.query_cypher.return_value = [{"name": "BFS", "type": "Algorithm"}]

        dummy_llm = self._DummyLLM(
            "cypher\nMATCH (e:Entity) RETURN e.name AS name, e.type AS type LIMIT 1"
        )

        with patch("kg_rag.tools.graph_query.ChatOpenAI", return_value=dummy_llm):
            tool = create_graph_query(mock_graph)
            result = await tool.ainvoke({"question": "Give me one entity"})

        called_cypher = mock_graph.query_cypher.call_args.args[0]
        assert called_cypher.lstrip().upper().startswith("MATCH")
        assert "[1]" in result

    @pytest.mark.asyncio
    async def test_fixes_truncated_match_keyword(self):
        from kg_rag.tools.graph_query import create_graph_query

        mock_graph = AsyncMock()
        mock_graph.query_cypher.return_value = [{"name": "BFS", "type": "Algorithm"}]

        dummy_llm = self._DummyLLM(
            "CH (e:Entity) RETURN e.name AS name, e.type AS type LIMIT 1"
        )

        with patch("kg_rag.tools.graph_query.ChatOpenAI", return_value=dummy_llm):
            tool = create_graph_query(mock_graph)
            result = await tool.ainvoke({"question": "Give me one entity"})

        called_cypher = mock_graph.query_cypher.call_args.args[0]
        first = called_cypher.lstrip().split(None, 1)[0].upper() if called_cypher.strip() else ""
        assert first == "MATCH"
        assert "[1]" in result

    @pytest.mark.asyncio
    async def test_no_records(self):
        from kg_rag.tools.graph_query import create_graph_query

        mock_graph = AsyncMock()
        mock_graph.query_cypher.return_value = []
        dummy_llm = self._DummyLLM("MATCH (n) RETURN n LIMIT 1")

        with patch("kg_rag.tools.graph_query.ChatOpenAI", return_value=dummy_llm):
            tool = create_graph_query(mock_graph)
            result = await tool.ainvoke({"question": "Any?"})

        assert "No results found" in result

    @pytest.mark.asyncio
    async def test_cypher_execution_error(self):
        from kg_rag.tools.graph_query import create_graph_query

        mock_graph = AsyncMock()
        mock_graph.query_cypher.side_effect = RuntimeError("bad cypher")
        dummy_llm = self._DummyLLM("MATCH (n) RETURN n")

        with patch("kg_rag.tools.graph_query.ChatOpenAI", return_value=dummy_llm):
            tool = create_graph_query(mock_graph)
            result = await tool.ainvoke({"question": "Run query"})

        assert "Graph query failed" in result
        assert "bad cypher" not in result  # internal details must not leak


class TestGraphQueryGuard:
    """Cypher injection prevention tests."""

    class _DummyLLM:
        def __init__(self, content: str):
            self._content = content

        async def ainvoke(self, _prompt):
            from types import SimpleNamespace
            return SimpleNamespace(content=self._content)

    @pytest.mark.asyncio
    async def test_rejects_write_keywords(self):
        from kg_rag.tools.graph_query import create_graph_query

        mock_graph = AsyncMock()
        for keyword in ("CREATE (n:Foo)", "MERGE (n:Foo)", "DELETE n", "DETACH DELETE n"):
            dummy_llm = self._DummyLLM(keyword)
            with patch("kg_rag.tools.graph_query.ChatOpenAI", return_value=dummy_llm):
                tool = create_graph_query(mock_graph)
                result = await tool.ainvoke({"question": "test"})
            assert "rejected" in result

    @pytest.mark.asyncio
    async def test_rejects_apoc(self):
        from kg_rag.tools.graph_query import create_graph_query

        mock_graph = AsyncMock()
        dummy_llm = self._DummyLLM("CALL apoc.do.when(true, 'CREATE (n)', '', {})")
        with patch("kg_rag.tools.graph_query.ChatOpenAI", return_value=dummy_llm):
            tool = create_graph_query(mock_graph)
            result = await tool.ainvoke({"question": "test"})
        assert "rejected" in result

    @pytest.mark.asyncio
    async def test_auto_appends_limit(self):
        from kg_rag.tools.graph_query import create_graph_query

        mock_graph = AsyncMock()
        mock_graph.query_cypher.return_value = [{"n": 1}]
        dummy_llm = self._DummyLLM("MATCH (n) RETURN n")
        with patch("kg_rag.tools.graph_query.ChatOpenAI", return_value=dummy_llm):
            tool = create_graph_query(mock_graph)
            await tool.ainvoke({"question": "test"})
        called_cypher = mock_graph.query_cypher.call_args.args[0]
        assert "LIMIT" in called_cypher

    @pytest.mark.asyncio
    async def test_comment_bypass_blocked(self):
        from kg_rag.tools.graph_query import create_graph_query

        mock_graph = AsyncMock()
        mock_graph.query_cypher.return_value = []
        # Attempt to hide CREATE behind a line comment
        dummy_llm = self._DummyLLM("MATCH (n) RETURN n\n// CREATE (x:Hack)")
        with patch("kg_rag.tools.graph_query.ChatOpenAI", return_value=dummy_llm):
            tool = create_graph_query(mock_graph)
            result = await tool.ainvoke({"question": "test"})
        # The comment is stripped, so CREATE is no longer visible — query should pass
        assert "rejected" not in result

        # But if CREATE is hidden inside a block comment to trick naive check
        dummy_llm2 = self._DummyLLM("MATCH (n) /* harmless */ CREATE (x:Hack) RETURN n")
        with patch("kg_rag.tools.graph_query.ChatOpenAI", return_value=dummy_llm2):
            tool = create_graph_query(mock_graph)
            result = await tool.ainvoke({"question": "test"})
        # CREATE is outside the comment — should be blocked
        assert "rejected" in result
