"""Tests for kg_rag.memory.profile.read_profile (formatting only)."""

import pytest
from unittest.mock import AsyncMock

from kg_rag.memory.profile import read_profile


class TestReadProfile:
    @pytest.mark.asyncio
    async def test_no_records(self):
        graph = AsyncMock()
        graph.query_cypher.return_value = []
        out = await read_profile("u1", graph)
        assert "no profile data" in out.lower()

    @pytest.mark.asyncio
    async def test_formats_sections(self):
        graph = AsyncMock()
        graph.query_cypher.return_value = [
            {"rel_type": "MASTERED", "name": "BFS", "confidence": 0.9},
            {"rel_type": "WEAK_AT", "name": "DP", "confidence": 0.4},
        ]
        out = await read_profile("u1", graph)
        assert "User: u1" in out
        assert "\nMASTERED:" in out
        assert "- BFS (confidence=0.9)" in out
        assert "\nWEAK_AT:" in out
        assert "- DP (confidence=0.4)" in out
