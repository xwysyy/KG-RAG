"""Tests for kg_rag.ingest.extract parsing helpers (no network calls)."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from kg_rag.ingest.extract import (
    _parse_extraction,
    dedup_by_alias_cross_ref,
    dedup_by_llm,
    merge_entities,
    remap_relations,
)
from kg_rag.models import Entity, Relation, make_entity_id


class TestParseExtraction:
    def test_strips_code_fences_and_parses(self):
        raw = (
            "```json\n"
            "{"
            '"entities": ['
            '{"name": "BFS", "type": "Algorithm", "description": "Graph traversal"},'
            '{"name": "Queue", "type": "DataStructure", "description": "FIFO structure"}'
            '],'
            '"relations": [{"source": "BFS", "target": "Queue", "type": "USES", "description": "uses a queue"}]'
            "}\n"
            "```"
        )
        entities, relations = _parse_extraction(raw, chunk_id="c1")

        assert len(entities) == 2
        e = entities[0]
        assert e.id == make_entity_id("BFS")
        assert e.name == "BFS"
        assert e.type == "Algorithm"
        assert e.description == "Graph traversal"
        assert e.source_chunks == ["c1"]

        assert len(relations) == 1
        r = relations[0]
        assert r.source == "BFS"
        assert r.target == "Queue"
        assert r.type == "USES"
        assert r.description == "uses a queue"

    def test_returns_empty_on_invalid_json(self):
        entities, relations = _parse_extraction("not json", chunk_id="c1")
        assert entities == []
        assert relations == []

    def test_skips_entities_with_missing_name(self):
        raw = '{"entities": [{"name": "   "}, {"type": "Algorithm"}], "relations": []}'
        entities, relations = _parse_extraction(raw, chunk_id="c1")
        assert entities == []
        assert relations == []

    def test_skips_relations_with_missing_endpoints(self):
        raw = (
            "{"
            '"entities": [{"name": "BFS"}, {"name": "Queue"}],'
            '"relations": ['
            '{"source": "BFS", "target": "", "type": "PREREQ"},'
            '{"source": "", "target": "Queue", "type": "USES"},'
            '{"source": "BFS", "target": "Queue"}'
            "]"
            "}"
        )
        entities, relations = _parse_extraction(raw, chunk_id="c1")
        assert len(entities) == 2
        assert len(relations) == 1
        assert relations[0].type == "RELATED_TO"

    def test_parses_aliases_from_llm_output(self):
        raw = (
            '{"entities": [{"name": "Breadth-First Search", "type": "Algorithm",'
            ' "description": "Graph traversal", "aliases": ["BFS", "广度优先搜索"]}],'
            ' "relations": []}'
        )
        entities, _ = _parse_extraction(raw, chunk_id="c1")
        assert len(entities) == 1
        assert entities[0].aliases == ["BFS", "广度优先搜索"]

    def test_aliases_defaults_empty_when_missing(self):
        raw = '{"entities": [{"name": "BFS"}], "relations": []}'
        entities, _ = _parse_extraction(raw, chunk_id="c1")
        assert entities[0].aliases == []


class TestEntityMergeStrategy:
    """Tests for merge_entities (shared production helper)."""

    def test_description_concatenation(self):
        e1 = Entity(id="a", name="BFS", type="Algorithm",
                     description="Graph traversal", source_chunks=["c1"])
        e2 = Entity(id="a", name="BFS", type="Algorithm",
                     description="Level-order search", source_chunks=["c2"])
        merged = merge_entities([[e1], [e2]])
        assert len(merged) == 1
        assert "Graph traversal" in merged[0].description
        assert "Level-order search" in merged[0].description

    def test_duplicate_description_not_repeated(self):
        e1 = Entity(id="a", name="BFS", description="desc", source_chunks=["c1"])
        e2 = Entity(id="a", name="BFS", description="desc", source_chunks=["c2"])
        merged = merge_entities([[e1], [e2]])
        assert merged[0].description == "desc"

    def test_type_majority_vote(self):
        e1 = Entity(id="a", name="BFS", type="Algorithm", source_chunks=["c1"])
        e2 = Entity(id="a", name="BFS", type="Concept", source_chunks=["c2"])
        e3 = Entity(id="a", name="BFS", type="Algorithm", source_chunks=["c3"])
        merged = merge_entities([[e1], [e2], [e3]])
        assert merged[0].type == "Algorithm"

    def test_no_alias_for_exact_same_name(self):
        e1 = Entity(id="a", name="BFS", source_chunks=["c1"])
        e2 = Entity(id="a", name="BFS", source_chunks=["c2"])
        merged = merge_entities([[e1], [e2]])
        assert len(merged) == 1
        assert merged[0].aliases == []

    def test_aliases_from_different_casing(self):
        e1 = Entity(id="a", name="Breadth-First Search", source_chunks=["c1"])
        e2 = Entity(id="a", name="Breadth-first search", source_chunks=["c2"])
        merged = merge_entities([[e1], [e2]])
        assert "Breadth-first search" in merged[0].aliases

    def test_source_chunks_merged(self):
        e1 = Entity(id="a", name="BFS", source_chunks=["c1"])
        e2 = Entity(id="a", name="BFS", source_chunks=["c2", "c3"])
        merged = merge_entities([[e1], [e2]])
        assert merged[0].source_chunks == ["c1", "c2", "c3"]

    def test_llm_aliases_merged_across_chunks(self):
        e1 = Entity(id="a", name="Breadth-First Search",
                     aliases=["BFS"], source_chunks=["c1"])
        e2 = Entity(id="a", name="Breadth-First Search",
                     aliases=["广度优先搜索"], source_chunks=["c2"])
        merged = merge_entities([[e1], [e2]])
        assert "BFS" in merged[0].aliases
        assert "广度优先搜索" in merged[0].aliases

    def test_alias_dedup(self):
        e1 = Entity(id="a", name="BFS", aliases=["Breadth-First Search"],
                     source_chunks=["c1"])
        e2 = Entity(id="a", name="BFS", aliases=["Breadth-First Search"],
                     source_chunks=["c2"])
        merged = merge_entities([[e1], [e2]])
        assert merged[0].aliases.count("Breadth-First Search") == 1

    def test_line_level_description_dedup(self):
        e1 = Entity(id="a", name="BFS", description="line1\nline2",
                     source_chunks=["c1"])
        e2 = Entity(id="a", name="BFS", description="line2\nline3",
                     source_chunks=["c2"])
        merged = merge_entities([[e1], [e2]])
        lines = merged[0].description.splitlines()
        assert lines.count("line2") == 1
        assert "line1" in lines
        assert "line3" in lines


class TestAliasCrossRefDedup:
    """Tests for dedup_by_alias_cross_ref (Layer 1)."""

    def test_merges_by_shared_alias(self):
        """Entity A has alias "X", entity B is named "X" → merge."""
        a = Entity(id="a", name="Breadth-First Search",
                   aliases=["BFS"], source_chunks=["c1"])
        b = Entity(id="b", name="BFS",
                   aliases=[], source_chunks=["c2"])
        merged, name_map = dedup_by_alias_cross_ref([a, b])
        assert len(merged) == 1
        assert merged[0].name == "Breadth-First Search"
        assert "BFS" in name_map

    def test_no_false_merge(self):
        """Entities with no overlapping tokens stay separate."""
        a = Entity(id="a", name="BFS", aliases=["广度优先搜索"],
                   source_chunks=["c1"])
        b = Entity(id="b", name="DFS", aliases=["深度优先搜索"],
                   source_chunks=["c2"])
        merged, name_map = dedup_by_alias_cross_ref([a, b])
        assert len(merged) == 2
        assert name_map == {}

    def test_transitive_merge(self):
        """A↔B↔C via shared aliases → all three merge."""
        a = Entity(id="a", name="Breadth-First Search",
                   aliases=["BFS"], source_chunks=["c1"])
        b = Entity(id="b", name="BFS",
                   aliases=["广度优先搜索"], source_chunks=["c2"])
        c = Entity(id="c", name="广度优先搜索",
                   aliases=[], source_chunks=["c3"])
        merged, name_map = dedup_by_alias_cross_ref([a, b, c])
        assert len(merged) == 1
        # All original names should map to the canonical
        canonical = merged[0].name
        for ent in [a, b, c]:
            if ent.name != canonical:
                assert name_map[ent.name] == canonical

    def test_name_map_correct(self):
        """name_map maps non-canonical names to canonical."""
        a = Entity(id="a", name="Shortest Path",
                   aliases=["SP"], source_chunks=["c1"])
        b = Entity(id="b", name="SP",
                   aliases=[], source_chunks=["c2"])
        merged, name_map = dedup_by_alias_cross_ref([a, b])
        assert len(merged) == 1
        assert name_map.get("SP") == "Shortest Path"

    def test_empty_input(self):
        merged, name_map = dedup_by_alias_cross_ref([])
        assert merged == []
        assert name_map == {}

    def test_single_entity(self):
        a = Entity(id="a", name="BFS", source_chunks=["c1"])
        merged, name_map = dedup_by_alias_cross_ref([a])
        assert len(merged) == 1
        assert name_map == {}

    def test_id_matches_canonical_name(self):
        """After dedup, entity.id must equal make_entity_id(entity.name)."""
        a = Entity(id=make_entity_id("Breadth-First Search"),
                   name="Breadth-First Search",
                   aliases=["BFS"], source_chunks=["c1"])
        b = Entity(id=make_entity_id("BFS"), name="BFS",
                   aliases=[], source_chunks=["c2"])
        merged, _ = dedup_by_alias_cross_ref([a, b])
        assert len(merged) == 1
        assert merged[0].id == make_entity_id(merged[0].name)

    def test_original_names_preserved_as_aliases(self):
        """Merged-away entity names must appear in aliases."""
        a = Entity(id="a", name="Breadth-First Search",
                   aliases=["BFS"], source_chunks=["c1"])
        b = Entity(id="b", name="BFS",
                   aliases=[], source_chunks=["c2"])
        merged, _ = dedup_by_alias_cross_ref([a, b])
        assert "BFS" in merged[0].aliases


class TestRemapRelations:
    """Tests for remap_relations."""

    def test_basic_remap(self):
        rels = [
            Relation(source="BFS", target="Queue", type="USES"),
        ]
        name_map = {"BFS": "Breadth-First Search"}
        result = remap_relations(rels, name_map)
        assert len(result) == 1
        assert result[0].source == "Breadth-First Search"
        assert result[0].target == "Queue"

    def test_drops_self_loops(self):
        rels = [
            Relation(source="BFS", target="Breadth-First Search", type="VARIANT_OF"),
        ]
        name_map = {"BFS": "Breadth-First Search"}
        result = remap_relations(rels, name_map)
        assert result == []

    def test_dedup_relations(self):
        rels = [
            Relation(source="BFS", target="Queue", type="USES", description="d1"),
            Relation(source="Breadth-First Search", target="Queue", type="USES", description="d2"),
        ]
        name_map = {"BFS": "Breadth-First Search"}
        result = remap_relations(rels, name_map)
        assert len(result) == 1
        assert result[0].source == "Breadth-First Search"

    def test_no_remap_when_empty_map(self):
        rels = [
            Relation(source="A", target="B", type="PREREQ"),
        ]
        result = remap_relations(rels, {})
        assert len(result) == 1
        assert result[0].source == "A"

    def test_empty_relations(self):
        result = remap_relations([], {"A": "B"})
        assert result == []

    def test_transitive_remap(self):
        """name_map A→B, B→C should resolve A to C."""
        rels = [
            Relation(source="A", target="D", type="USES"),
        ]
        name_map = {"A": "B", "B": "C"}
        result = remap_relations(rels, name_map)
        assert len(result) == 1
        assert result[0].source == "C"

    def test_preserves_weight(self):
        rels = [
            Relation(source="A", target="B", type="USES", weight=2.5),
        ]
        result = remap_relations(rels, {"A": "X"})
        assert result[0].weight == 2.5


class TestDedupByLlm:
    """Tests for dedup_by_llm (Layer 2)."""

    def _make_entity(self, name: str, aliases: list[str] | None = None) -> Entity:
        return Entity(
            id=make_entity_id(name),
            name=name,
            aliases=aliases or [],
            source_chunks=["c1"],
        )

    def _mock_llm(self, content: str) -> AsyncMock:
        llm = AsyncMock()
        llm.ainvoke.return_value = SimpleNamespace(content=content)
        return llm

    @pytest.mark.asyncio
    async def test_single_entity_returns_unchanged(self):
        ent = self._make_entity("BFS")
        llm = self._mock_llm("")
        result, name_map = await dedup_by_llm([ent], llm)
        assert len(result) == 1
        assert name_map == {}
        llm.ainvoke.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_valid_groups_merge(self):
        a = self._make_entity("Breadth-First Search", aliases=["BFS"])
        b = self._make_entity("BFS traversal")
        resp = json.dumps({
            "groups": [{"canonical": "Breadth-First Search", "duplicates": ["BFS traversal"]}]
        })
        llm = self._mock_llm(resp)
        result, name_map = await dedup_by_llm([a, b], llm)
        assert len(result) == 1
        assert result[0].name == "Breadth-First Search"
        assert name_map == {"BFS traversal": "Breadth-First Search"}

    @pytest.mark.asyncio
    async def test_empty_groups_no_change(self):
        a = self._make_entity("BFS")
        b = self._make_entity("DFS")
        llm = self._mock_llm(json.dumps({"groups": []}))
        result, name_map = await dedup_by_llm([a, b], llm)
        assert len(result) == 2
        assert name_map == {}

    @pytest.mark.asyncio
    async def test_invalid_json_fallback(self):
        a = self._make_entity("BFS")
        b = self._make_entity("DFS")
        llm = self._mock_llm("this is not json at all")
        result, name_map = await dedup_by_llm([a, b], llm)
        assert len(result) == 2
        assert name_map == {}

    @pytest.mark.asyncio
    async def test_canonical_not_in_set_skipped(self):
        a = self._make_entity("BFS")
        b = self._make_entity("DFS")
        resp = json.dumps({
            "groups": [{"canonical": "NonExistent", "duplicates": ["BFS"]}]
        })
        llm = self._mock_llm(resp)
        result, name_map = await dedup_by_llm([a, b], llm)
        assert len(result) == 2
        assert name_map == {}

    @pytest.mark.asyncio
    async def test_non_dict_group_skipped(self):
        a = self._make_entity("BFS")
        b = self._make_entity("DFS")
        resp = json.dumps({"groups": ["not a dict", 42]})
        llm = self._mock_llm(resp)
        result, name_map = await dedup_by_llm([a, b], llm)
        assert len(result) == 2
        assert name_map == {}

    @pytest.mark.asyncio
    async def test_non_string_dup_skipped(self):
        a = self._make_entity("BFS")
        b = self._make_entity("DFS")
        resp = json.dumps({
            "groups": [{"canonical": "BFS", "duplicates": [123, None]}]
        })
        llm = self._mock_llm(resp)
        result, name_map = await dedup_by_llm([a, b], llm)
        assert len(result) == 2
        assert name_map == {}

    @pytest.mark.asyncio
    async def test_dup_name_preserved_as_alias(self):
        a = self._make_entity("Breadth-First Search")
        b = self._make_entity("BFS traversal")
        resp = json.dumps({
            "groups": [{"canonical": "Breadth-First Search", "duplicates": ["BFS traversal"]}]
        })
        llm = self._mock_llm(resp)
        result, _ = await dedup_by_llm([a, b], llm)
        assert "BFS traversal" in result[0].aliases

    @pytest.mark.asyncio
    async def test_id_recomputed(self):
        a = self._make_entity("Breadth-First Search")
        b = self._make_entity("BFS traversal")
        resp = json.dumps({
            "groups": [{"canonical": "Breadth-First Search", "duplicates": ["BFS traversal"]}]
        })
        llm = self._mock_llm(resp)
        result, _ = await dedup_by_llm([a, b], llm)
        assert result[0].id == make_entity_id("Breadth-First Search")


class TestEndpointValidation:
    """Tests for relation endpoint validation in _parse_extraction (#5)."""

    def test_valid_endpoints_kept(self):
        raw = json.dumps({
            "entities": [
                {"name": "BFS", "type": "Algorithm"},
                {"name": "Queue", "type": "DataStructure"},
            ],
            "relations": [
                {"source": "BFS", "target": "Queue", "type": "USES"},
            ],
        })
        entities, relations = _parse_extraction(raw, chunk_id="c1")
        assert len(entities) == 2
        assert len(relations) == 1

    def test_invalid_source_dropped(self):
        raw = json.dumps({
            "entities": [
                {"name": "BFS", "type": "Algorithm"},
            ],
            "relations": [
                {"source": "NonExistent", "target": "BFS", "type": "PREREQ"},
            ],
        })
        entities, relations = _parse_extraction(raw, chunk_id="c1")
        assert len(entities) == 1
        assert len(relations) == 0

    def test_invalid_target_dropped(self):
        raw = json.dumps({
            "entities": [
                {"name": "BFS", "type": "Algorithm"},
            ],
            "relations": [
                {"source": "BFS", "target": "NonExistent", "type": "USES"},
            ],
        })
        entities, relations = _parse_extraction(raw, chunk_id="c1")
        assert len(entities) == 1
        assert len(relations) == 0

    def test_mixed_valid_and_invalid(self):
        raw = json.dumps({
            "entities": [
                {"name": "BFS", "type": "Algorithm"},
                {"name": "Queue", "type": "DataStructure"},
            ],
            "relations": [
                {"source": "BFS", "target": "Queue", "type": "USES"},
                {"source": "BFS", "target": "Ghost", "type": "PREREQ"},
                {"source": "Ghost", "target": "Queue", "type": "RELATED_TO"},
            ],
        })
        entities, relations = _parse_extraction(raw, chunk_id="c1")
        assert len(entities) == 2
        assert len(relations) == 1
        assert relations[0].source == "BFS"
        assert relations[0].target == "Queue"
