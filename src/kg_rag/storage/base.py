"""Abstract base classes for storage backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseVectorStore(ABC):
    """Interface for vector similarity search backends."""

    @abstractmethod
    async def query(
        self, query: str, top_k: int = 5, *, query_embedding: list[float] | None = None
    ) -> list[dict[str, Any]]:
        """Return top-k similar records.  Each dict contains at least
        ``id``, ``distance``, and the stored metadata fields."""

    @abstractmethod
    async def upsert(self, data: dict[str, dict[str, Any]]) -> None:
        """Insert or update records.  *data* maps ``id -> {content, metadata…}``."""

    @abstractmethod
    async def delete(self, ids: list[str]) -> None:
        """Delete records by id."""

    async def initialize(self) -> None:  # noqa: B027
        """Optional one-time setup (create indexes, etc.)."""

    async def finalize(self) -> None:  # noqa: B027
        """Optional cleanup (flush to disk, close connections)."""


class BaseGraphStore(ABC):
    """Interface for labelled-property-graph backends (Neo4j, etc.)."""

    # -- node operations -----------------------------------------------------

    @abstractmethod
    async def has_node(self, node_id: str) -> bool: ...

    @abstractmethod
    async def get_node(self, node_id: str) -> dict[str, Any] | None: ...

    @abstractmethod
    async def upsert_node(self, node_id: str, node_data: dict[str, Any]) -> None: ...

    @abstractmethod
    async def delete_node(self, node_id: str) -> None: ...

    # -- edge operations -----------------------------------------------------

    @abstractmethod
    async def has_edge(self, source: str, target: str) -> bool: ...

    @abstractmethod
    async def get_edge(self, source: str, target: str) -> dict[str, Any] | None: ...

    @abstractmethod
    async def upsert_edge(
        self, source: str, target: str, edge_data: dict[str, Any]
    ) -> None: ...

    # -- query ---------------------------------------------------------------

    @abstractmethod
    async def query_cypher(
        self, cypher: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]: ...

    # -- lifecycle -----------------------------------------------------------

    async def initialize(self) -> None:  # noqa: B027
        """Create constraints / indexes."""

    async def finalize(self) -> None:  # noqa: B027
        """Close driver / release resources."""
