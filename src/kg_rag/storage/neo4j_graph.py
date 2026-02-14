"""Neo4j async graph store implementation."""

from __future__ import annotations

import logging
from typing import Any

from neo4j import AsyncGraphDatabase, AsyncDriver
from neo4j.exceptions import TransientError, ServiceUnavailable
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from kg_rag.config import settings
from kg_rag.models import ENTITY_TYPE_LABELS, KNOWLEDGE_REL_TYPES, PROFILE_REL_TYPES
from kg_rag.storage.base import BaseGraphStore

logger = logging.getLogger(__name__)

_TRANSIENT = (TransientError, ServiceUnavailable)

_retry_read = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(_TRANSIENT),
    reraise=True,
)

_retry_write = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(_TRANSIENT),
    reraise=True,
)


class Neo4jGraphStore(BaseGraphStore):
    """Async Neo4j driver wrapper implementing BaseGraphStore."""

    def __init__(self) -> None:
        self._driver: AsyncDriver | None = None

    # -- lifecycle -----------------------------------------------------------

    async def initialize(self) -> None:
        self._driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_username, settings.neo4j_password),
        )
        # create constraints / indexes
        async with self._driver.session(database=settings.neo4j_database) as session:
            for lbl in ("Entity", *sorted(ENTITY_TYPE_LABELS)):
                try:
                    result = await session.run(
                        f"CREATE CONSTRAINT IF NOT EXISTS "
                        f"FOR (e:{lbl}) REQUIRE e.entity_id IS UNIQUE"
                    )
                    await result.consume()
                except Exception as exc:
                    logger.warning(
                        "Failed to create constraint for %s: %s (may lack privileges)",
                        lbl, exc,
                    )
            try:
                result = await session.run(
                    "CREATE CONSTRAINT IF NOT EXISTS "
                    "FOR (u:User) REQUIRE u.user_id IS UNIQUE"
                )
                await result.consume()
            except Exception as exc:
                logger.warning(
                    "Failed to create constraint for User: %s (may lack privileges)",
                    exc,
                )
        logger.info("Neo4j initialized (uri=%s)", settings.neo4j_uri)

    async def finalize(self) -> None:
        if self._driver:
            await self._driver.close()
            self._driver = None

    # -- helpers -------------------------------------------------------------

    def _session(self):
        if self._driver is None:
            raise RuntimeError("Call initialize() first")
        return self._driver.session(database=settings.neo4j_database)

    # -- node operations -----------------------------------------------------

    @_retry_read
    async def has_node(self, node_id: str) -> bool:
        async with self._session() as session:
            result = await session.run(
                "MATCH (n:Entity {entity_id: $eid}) RETURN count(n) > 0 AS exists",
                eid=node_id,
            )
            record = await result.single()
            return bool(record and record["exists"])

    @_retry_read
    async def get_node(self, node_id: str) -> dict[str, Any] | None:
        async with self._session() as session:
            result = await session.run(
                "MATCH (n:Entity {entity_id: $eid}) RETURN properties(n) AS props",
                eid=node_id,
            )
            record = await result.single()
            return dict(record["props"]) if record else None

    _BASE_LABELS = {"Entity", "User"}
    _ENTITY_TYPE_LABELS = ENTITY_TYPE_LABELS

    _ALLOWED_REL_TYPES = KNOWLEDGE_REL_TYPES | PROFILE_REL_TYPES

    @_retry_write
    async def upsert_node(self, node_id: str, node_data: dict[str, Any]) -> None:
        data = dict(node_data)  # avoid mutating caller's dict
        label = data.pop("label", "Entity")
        props = {**data, "entity_id": node_id}

        if label in self._ENTITY_TYPE_LABELS:
            # Known entity type: MERGE on :Entity, then add type label
            props.setdefault("type", label)
            cypher = (
                "MERGE (n:Entity {entity_id: $eid}) "
                "SET n += $props "
                f"SET n:{label}"
            )
        elif label not in self._BASE_LABELS:
            # Unknown type: fall back to :Entity, store in type property
            props["type"] = label
            cypher = (
                "MERGE (n:Entity {entity_id: $eid}) "
                "SET n += $props"
            )
        else:
            # Base label: User uses user_id as primary key, Entity uses entity_id
            if label == "User":
                cypher = (
                    "MERGE (n:User {user_id: $eid}) "
                    "SET n += $props"
                )
            else:
                cypher = (
                    f"MERGE (n:{label} {{entity_id: $eid}}) "
                    "SET n += $props"
                )

        async with self._session() as session:
            result = await session.run(cypher, eid=node_id, props=props)
            await result.consume()

    @_retry_write
    async def delete_node(self, node_id: str) -> None:
        async with self._session() as session:
            result = await session.run(
                "MATCH (n:Entity {entity_id: $eid}) DETACH DELETE n",
                eid=node_id,
            )
            await result.consume()

    # -- edge operations -----------------------------------------------------

    @_retry_read
    async def has_edge(self, source: str, target: str) -> bool:
        async with self._session() as session:
            result = await session.run(
                "MATCH (:Entity {entity_id: $src})-[r]->(:Entity {entity_id: $tgt}) "
                "RETURN count(r) > 0 AS exists",
                src=source,
                tgt=target,
            )
            record = await result.single()
            return bool(record and record["exists"])

    @_retry_read
    async def get_edge(self, source: str, target: str) -> dict[str, Any] | None:
        async with self._session() as session:
            result = await session.run(
                "MATCH (:Entity {entity_id: $src})-[r]->(:Entity {entity_id: $tgt}) "
                "RETURN properties(r) AS props, type(r) AS rel_type LIMIT 1",
                src=source,
                tgt=target,
            )
            record = await result.single()
            if not record:
                return None
            props = dict(record["props"])
            props["type"] = record["rel_type"]
            return props

    @_retry_write
    async def upsert_edge(
        self, source: str, target: str, edge_data: dict[str, Any]
    ) -> None:
        data = dict(edge_data)  # avoid mutating caller's dict
        rel_type = data.pop("type", "RELATED_TO")
        if rel_type not in self._ALLOWED_REL_TYPES:
            logger.warning(
                "Unknown rel type %r mapped to RELATED_TO", rel_type
            )
            data["original_type"] = rel_type
            rel_type = "RELATED_TO"
        cypher = (
            "MATCH (a {entity_id: $src}), (b {entity_id: $tgt}) "
            f"MERGE (a)-[r:{rel_type}]->(b) "
            "SET r += $props"
        )
        async with self._session() as session:
            result = await session.run(cypher, src=source, tgt=target, props=data)
            summary = await result.consume()
            if summary.counters.relationships_created == 0 and summary.counters.properties_set == 0:
                logger.warning(
                    "upsert_edge(%s, %s): no relationship created/updated — "
                    "endpoint(s) may not exist",
                    source, target,
                )

    # -- cypher query --------------------------------------------------------

    @_retry_read
    async def query_cypher(
        self, cypher: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        async with self._session() as session:
            result = await session.run(cypher, **(params or {}))
            records = [record.data() async for record in result]
            return records
