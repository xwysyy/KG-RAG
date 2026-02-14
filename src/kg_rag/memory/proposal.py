"""Proposal-based write mechanism for user profile updates.

Extracts profile change proposals from conversations, filters by
confidence threshold, and applies them to Neo4j.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from kg_rag.agent.prompts import PROFILE_EXTRACTION_PROMPT
from kg_rag.config import settings
from kg_rag.models import PROFILE_REL_TYPES, UserProfileUpdate, make_entity_id
from kg_rag.storage.base import BaseGraphStore
from kg_rag.utils import strip_code_fences

logger = logging.getLogger(__name__)


async def extract_proposals(
    conversation: str, user_id: str
) -> list[UserProfileUpdate]:
    """Use LLM to extract profile change proposals from a conversation."""

    llm = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        temperature=0,
    )

    prompt = PROFILE_EXTRACTION_PROMPT.format(conversation=conversation)
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    raw = response.content.strip()

    # Parse JSON array from LLM output
    proposals: list[UserProfileUpdate] = []
    try:
        cleaned = strip_code_fences(raw)

        start = cleaned.find("[")
        end = cleaned.rfind("]")
        if start != -1 and end != -1:
            items = json.loads(cleaned[start : end + 1])
            for item in items:
                try:
                    if isinstance(item, dict):
                        item.pop("user_id", None)
                    proposals.append(
                        UserProfileUpdate(user_id=user_id, **item)
                    )
                except (TypeError, ValueError) as e:
                    logger.warning("Skipping invalid proposal item %r: %s", item, e)
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning("Failed to parse profile proposals: %s", e)

    logger.info("Extracted %d profile proposals for user %s", len(proposals), user_id)
    return proposals


def filter_proposals(
    proposals: list[UserProfileUpdate], threshold: float = 0.7
) -> list[UserProfileUpdate]:
    """Keep only proposals whose confidence meets the threshold."""

    accepted = [p for p in proposals if p.confidence >= threshold]
    dropped = len(proposals) - len(accepted)
    if dropped:
        logger.info("Filtered out %d low-confidence proposals (threshold=%.2f)",
                     dropped, threshold)
    return accepted


_ALLOWED_PROFILE_RELS = PROFILE_REL_TYPES


async def apply_proposals(
    proposals: list[UserProfileUpdate], graph: BaseGraphStore
) -> int:
    """Write accepted proposals to Neo4j. Returns the number applied."""

    applied = 0
    for p in proposals:
        if p.relation_type not in _ALLOWED_PROFILE_RELS:
            logger.warning(
                "Skipping proposal with invalid relation_type %r for %s",
                p.relation_type, p.target_entity,
            )
            continue
        try:
            # Ensure User node exists
            await graph.upsert_node(
                p.user_id, {"label": "User", "user_id": p.user_id}
            )
            # Ensure target entity node exists
            # Stub node — type unknown from conversation context.
            # If entity was previously ingested, MERGE preserves existing type labels.
            entity_id = make_entity_id(p.target_entity)
            await graph.upsert_node(
                entity_id,
                {"label": "Entity", "name": p.target_entity},
            )
            # Upsert the relationship
            await graph.upsert_edge(
                p.user_id,
                entity_id,
                {
                    "type": p.relation_type,
                    "confidence": p.confidence,
                    "evidence": p.evidence,
                    "last_updated": datetime.now(tz=timezone.utc).isoformat(),
                },
            )
            applied += 1
        except Exception as e:
            logger.warning(
                "Failed to apply proposal %s->%s: %s",
                p.user_id, p.target_entity, e,
            )

    logger.info("Applied %d/%d proposals", applied, len(proposals))
    return applied
