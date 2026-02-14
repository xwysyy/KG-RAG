"""Pydantic data models — unified definitions for the entire project."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

# Canonical set of known entity-type labels used across the project.
# Neo4j dual-label scheme, extraction prompts, and graph schema all derive from this.
ENTITY_TYPE_LABELS: frozenset[str] = frozenset({
    "Algorithm", "DataStructure", "Concept", "Problem", "Technique",
})

# Canonical set of knowledge-graph relation types.
KNOWLEDGE_REL_TYPES: frozenset[str] = frozenset({
    "PREREQ", "IMPROVES", "APPLIES_TO", "BELONGS_TO",
    "VARIANT_OF", "USES", "RELATED_TO",
})

# User-profile relation types.
PROFILE_REL_TYPES: frozenset[str] = frozenset({
    "MASTERED", "WEAK_AT", "INTERESTED_IN",
})


def make_entity_id(name: str) -> str:
    """Canonical entity ID: SHA-256 of lowered+stripped name."""
    return hashlib.sha256(name.lower().strip().encode()).hexdigest()


# ---------------------------------------------------------------------------
# Knowledge Graph primitives
# ---------------------------------------------------------------------------

class Entity(BaseModel):
    """A node in the knowledge graph."""

    id: str
    name: str
    type: str = "Algorithm"
    description: str = ""
    source_chunks: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)


class Relation(BaseModel):
    """An edge in the knowledge graph."""

    source: str
    target: str
    type: str
    description: str = ""
    weight: float = 1.0


# ---------------------------------------------------------------------------
# Text chunk
# ---------------------------------------------------------------------------

class TextChunk(BaseModel):
    """A chunk of ingested text with metadata."""

    id: str
    content: str
    doc_id: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Query / retrieval results
# ---------------------------------------------------------------------------

class QueryResult(BaseModel):
    """Aggregated retrieval result from vector + graph stores."""

    chunks: list[TextChunk] = Field(default_factory=list)
    entities: list[Entity] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# User profile
# ---------------------------------------------------------------------------

class UserProfileUpdate(BaseModel):
    """A single proposed change to a user's profile in Neo4j."""

    user_id: str
    relation_type: str  # e.g. MASTERED, WEAK_AT, INTERESTED_IN
    target_entity: str  # entity name
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
