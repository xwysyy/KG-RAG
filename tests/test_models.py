"""Tests for kg_rag.models."""

import pytest
from kg_rag.models import (
    Entity,
    Relation,
    TextChunk,
    QueryResult,
    UserProfileUpdate,
    make_entity_id,
)


class TestMakeEntityId:
    def test_deterministic(self):
        assert make_entity_id("BFS") == make_entity_id("BFS")

    def test_case_insensitive(self):
        assert make_entity_id("BFS") == make_entity_id("bfs")

    def test_strips_whitespace(self):
        assert make_entity_id("BFS") == make_entity_id("  BFS  ")

    def test_different_names_differ(self):
        assert make_entity_id("BFS") != make_entity_id("DFS")


class TestEntity:
    def test_defaults(self):
        e = Entity(id="abc", name="BFS")
        assert e.type == "Algorithm"
        assert e.description == ""
        assert e.source_chunks == []

    def test_custom_type(self):
        e = Entity(id="abc", name="BFS", type="DataStructure")
        assert e.type == "DataStructure"


class TestRelation:
    def test_required_fields(self):
        r = Relation(source="a", target="b", type="PREREQ")
        assert r.weight == 1.0

    def test_custom_weight(self):
        r = Relation(source="a", target="b", type="PREREQ", weight=0.5)
        assert r.weight == 0.5


class TestUserProfileUpdate:
    def test_confidence_bounds(self):
        with pytest.raises(Exception):
            UserProfileUpdate(
                user_id="u1",
                relation_type="MASTERED",
                target_entity="BFS",
                confidence=1.5,
            )

    def test_valid_creation(self):
        p = UserProfileUpdate(
            user_id="u1",
            relation_type="MASTERED",
            target_entity="BFS",
            confidence=0.9,
            evidence="solved 10 BFS problems",
        )
        assert p.confidence == 0.9
        assert p.timestamp is not None

    def test_timestamp_is_utc(self):
        from datetime import timezone
        p = UserProfileUpdate(
            user_id="u1",
            relation_type="MASTERED",
            target_entity="BFS",
            confidence=0.9,
        )
        assert p.timestamp.tzinfo is not None
        assert p.timestamp.tzinfo == timezone.utc
