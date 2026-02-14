"""User profile CRUD operations backed by Neo4j."""

from __future__ import annotations

import logging

from kg_rag.storage.neo4j_graph import Neo4jGraphStore

logger = logging.getLogger(__name__)


async def read_profile(user_id: str, graph: Neo4jGraphStore) -> str:
    """Read a user's profile from Neo4j and return a formatted string.

    The profile includes mastered algorithms, weak concepts, and interests.
    """
    cypher = """
    MATCH (u:User {user_id: $uid})
    OPTIONAL MATCH (u)-[r]->(t)
    RETURN type(r) AS rel_type,
           t.entity_id AS entity,
           t.name AS name,
           r.confidence AS confidence,
           r.evidence AS evidence,
           r.last_updated AS last_updated
    ORDER BY rel_type, r.confidence DESC
    """
    records = await graph.query_cypher(cypher, {"uid": user_id})

    if not records:
        return f"User {user_id}: no profile data yet."

    sections: dict[str, list[str]] = {}
    for rec in records:
        rel = rec.get("rel_type")
        if not rel:
            continue
        name = rec.get("name") or rec.get("entity", "?")
        conf = rec.get("confidence", "?")
        line = f"  - {name} (confidence={conf})"
        sections.setdefault(rel, []).append(line)

    if not sections:
        return f"User {user_id}: no profile data yet."

    parts = [f"User: {user_id}"]
    for rel_type, lines in sections.items():
        parts.append(f"\n{rel_type}:")
        parts.extend(lines)

    return "\n".join(parts)
