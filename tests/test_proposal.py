"""Tests for kg_rag.memory.proposal — filter, extract, apply."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from kg_rag.models import UserProfileUpdate


class TestFilterProposals:
    def _make(self, confidence: float) -> UserProfileUpdate:
        return UserProfileUpdate(
            user_id="u1",
            relation_type="MASTERED",
            target_entity="BFS",
            confidence=confidence,
            evidence="test",
        )

    def test_above_threshold_kept(self):
        from kg_rag.memory.proposal import filter_proposals

        proposals = [self._make(0.9), self._make(0.8)]
        assert len(filter_proposals(proposals, threshold=0.7)) == 2

    def test_below_threshold_dropped(self):
        from kg_rag.memory.proposal import filter_proposals

        proposals = [self._make(0.3), self._make(0.5)]
        assert len(filter_proposals(proposals, threshold=0.7)) == 0

    def test_exact_threshold_kept(self):
        from kg_rag.memory.proposal import filter_proposals

        proposals = [self._make(0.7)]
        assert len(filter_proposals(proposals, threshold=0.7)) == 1

    def test_empty_list(self):
        from kg_rag.memory.proposal import filter_proposals

        assert filter_proposals([], threshold=0.7) == []

    def test_mixed(self):
        from kg_rag.memory.proposal import filter_proposals

        proposals = [self._make(0.9), self._make(0.5), self._make(0.7)]
        result = filter_proposals(proposals, threshold=0.7)
        assert len(result) == 2
        assert all(p.confidence >= 0.7 for p in result)


class TestExtractProposals:
    """Tests for extract_proposals (LLM-based extraction)."""

    def _mock_llm(self, content: str):
        llm = AsyncMock()
        llm.ainvoke.return_value = SimpleNamespace(content=content)
        return llm

    @pytest.mark.asyncio
    async def test_valid_proposals_extracted(self):
        from kg_rag.memory.proposal import extract_proposals

        items = [
            {
                "relation_type": "MASTERED",
                "target_entity": "BFS",
                "confidence": 0.9,
                "evidence": "User explained BFS clearly",
            }
        ]
        llm = self._mock_llm(json.dumps(items))
        with patch("kg_rag.memory.proposal.ChatOpenAI", return_value=llm):
            result = await extract_proposals("conv text", "u1")
        assert len(result) == 1
        assert result[0].relation_type == "MASTERED"
        assert result[0].target_entity == "BFS"
        assert result[0].user_id == "u1"

    @pytest.mark.asyncio
    async def test_invalid_json_returns_empty(self):
        from kg_rag.memory.proposal import extract_proposals

        llm = self._mock_llm("this is not json")
        with patch("kg_rag.memory.proposal.ChatOpenAI", return_value=llm):
            result = await extract_proposals("conv", "u1")
        assert result == []

    @pytest.mark.asyncio
    async def test_empty_array(self):
        from kg_rag.memory.proposal import extract_proposals

        llm = self._mock_llm("[]")
        with patch("kg_rag.memory.proposal.ChatOpenAI", return_value=llm):
            result = await extract_proposals("conv", "u1")
        assert result == []

    @pytest.mark.asyncio
    async def test_invalid_items_skipped(self):
        from kg_rag.memory.proposal import extract_proposals

        items = [
            {
                "relation_type": "MASTERED",
                "target_entity": "BFS",
                "confidence": 0.9,
                "evidence": "good",
            },
            "not a dict",
            {"missing_keys": True},
        ]
        llm = self._mock_llm(json.dumps(items))
        with patch("kg_rag.memory.proposal.ChatOpenAI", return_value=llm):
            result = await extract_proposals("conv", "u1")
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_markdown_fences_stripped(self):
        from kg_rag.memory.proposal import extract_proposals

        items = [
            {
                "relation_type": "WEAK_AT",
                "target_entity": "DP",
                "confidence": 0.8,
                "evidence": "struggled",
            }
        ]
        raw = f"```json\n{json.dumps(items)}\n```"
        llm = self._mock_llm(raw)
        with patch("kg_rag.memory.proposal.ChatOpenAI", return_value=llm):
            result = await extract_proposals("conv", "u1")
        assert len(result) == 1
        assert result[0].target_entity == "DP"

    @pytest.mark.asyncio
    async def test_user_id_overridden(self):
        from kg_rag.memory.proposal import extract_proposals

        items = [
            {
                "user_id": "wrong_user",
                "relation_type": "INTERESTED_IN",
                "target_entity": "Graph",
                "confidence": 0.75,
                "evidence": "asked about graphs",
            }
        ]
        llm = self._mock_llm(json.dumps(items))
        with patch("kg_rag.memory.proposal.ChatOpenAI", return_value=llm):
            result = await extract_proposals("conv", "correct_user")
        assert len(result) == 1
        assert result[0].user_id == "correct_user"


class TestApplyProposals:
    """Tests for apply_proposals (graph write)."""

    def _make_proposal(
        self, rel_type: str = "MASTERED", entity: str = "BFS", confidence: float = 0.9
    ) -> UserProfileUpdate:
        return UserProfileUpdate(
            user_id="u1",
            relation_type=rel_type,
            target_entity=entity,
            confidence=confidence,
            evidence="test evidence",
        )

    @pytest.mark.asyncio
    async def test_applies_valid_proposal(self):
        from kg_rag.memory.proposal import apply_proposals

        mock_graph = AsyncMock()
        proposals = [self._make_proposal()]
        count = await apply_proposals(proposals, mock_graph)
        assert count == 1
        assert mock_graph.upsert_node.await_count == 2  # User + Entity
        assert mock_graph.upsert_edge.await_count == 1

    @pytest.mark.asyncio
    async def test_skips_invalid_relation_type(self):
        from kg_rag.memory.proposal import apply_proposals

        mock_graph = AsyncMock()
        proposals = [self._make_proposal(rel_type="INVALID_TYPE")]
        count = await apply_proposals(proposals, mock_graph)
        assert count == 0
        mock_graph.upsert_node.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_graph_error_handled(self):
        from kg_rag.memory.proposal import apply_proposals

        mock_graph = AsyncMock()
        mock_graph.upsert_node.side_effect = RuntimeError("Neo4j down")
        proposals = [self._make_proposal()]
        count = await apply_proposals(proposals, mock_graph)
        assert count == 0

    @pytest.mark.asyncio
    async def test_multiple_proposals(self):
        from kg_rag.memory.proposal import apply_proposals

        mock_graph = AsyncMock()
        proposals = [
            self._make_proposal(entity="BFS"),
            self._make_proposal(rel_type="WEAK_AT", entity="DP"),
        ]
        count = await apply_proposals(proposals, mock_graph)
        assert count == 2

    @pytest.mark.asyncio
    async def test_empty_proposals(self):
        from kg_rag.memory.proposal import apply_proposals

        mock_graph = AsyncMock()
        count = await apply_proposals([], mock_graph)
        assert count == 0
        mock_graph.upsert_node.assert_not_awaited()
