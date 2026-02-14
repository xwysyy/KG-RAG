"""Graph query tool — NL → Cypher → Neo4j execution."""

from __future__ import annotations

import logging
import re

from neo4j.exceptions import ClientError
from langchain_core.tools import BaseTool, tool
from langchain_openai import ChatOpenAI

from kg_rag.config import settings
from kg_rag.agent.prompts import CYPHER_GENERATION_PROMPT
from kg_rag.models import ENTITY_TYPE_LABELS
from kg_rag.storage.base import BaseGraphStore
from kg_rag.utils import strip_code_fences

logger = logging.getLogger(__name__)


def _strip_cypher_comments(cypher: str) -> str:
    """Remove // and /* */ comments from Cypher before safety checks."""
    # Remove block comments
    cypher = re.sub(r"/\*.*?\*/", " ", cypher, flags=re.DOTALL)
    # Remove line comments
    cypher = re.sub(r"//[^\n]*", " ", cypher)
    return cypher


# Write-operation keywords that must never appear in LLM-generated Cypher.
# Checked case-insensitively as whole words (word-boundary regex).
_CYPHER_WRITE_KEYWORDS = [
    "CREATE", "MERGE", "DELETE", "DETACH", "SET", "REMOVE",
    "DROP", "CALL", "LOAD CSV", "FOREACH",
]
_WRITE_PATTERN = re.compile(
    r"\b(" + "|".join(_CYPHER_WRITE_KEYWORDS) + r")\b",
    re.IGNORECASE,
)
# Also block apoc procedures
_APOC_PATTERN = re.compile(r"\bapoc\.", re.IGNORECASE)

_DEFAULT_LIMIT = 50

_CYPHER_START_KEYWORDS = {"MATCH", "OPTIONAL", "WITH", "UNWIND", "RETURN"}
_FIRST_KEYWORD_PATTERN = re.compile(r"^\s*([A-Za-z]+)", re.IGNORECASE)
_RETURN_PATTERN = re.compile(r"\bRETURN\b", re.IGNORECASE)
_LIMIT_PATTERN = re.compile(r"\bLIMIT\b", re.IGNORECASE)


def _normalize_cypher(raw: str) -> str:
    """Normalize common formatting noise from LLM Cypher outputs.

    We keep this conservative and deterministic:
    - Drop a leading standalone language tag line like "cypher".
    - Fix a truncated leading keyword like "CH" -> "MATCH".
    """
    text = strip_code_fences(raw).strip()
    if not text:
        return text

    # Some models emit:
    #   cypher
    #   MATCH ...
    lines = text.splitlines()
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i < len(lines):
        first = lines[i].strip().lower()
        if first in {"cypher", "cql", "query"} or first.startswith("cypher:"):
            i += 1
            while i < len(lines) and not lines[i].strip():
                i += 1
    text = "\n".join(lines[i:]).strip()
    if not text:
        return text

    # Another observed failure mode is "CH (...)" where "MATCH" was truncated.
    m = _FIRST_KEYWORD_PATTERN.match(text)
    if m is not None and m.group(1).upper() == "CH":
        text = _FIRST_KEYWORD_PATTERN.sub("MATCH", text, count=1)

    return text


def _validate_read_cypher(cypher: str) -> tuple[bool, str]:
    stripped = _strip_cypher_comments(cypher).strip()
    if not stripped:
        return False, "empty query"

    if _WRITE_PATTERN.search(stripped) or _APOC_PATTERN.search(stripped):
        return False, "unsafe keyword detected"

    m = _FIRST_KEYWORD_PATTERN.match(stripped)
    if m is None:
        return False, "missing leading clause keyword"

    first = m.group(1).upper()
    if first not in _CYPHER_START_KEYWORDS:
        return False, f"unexpected leading clause keyword: {first}"

    if not _RETURN_PATTERN.search(stripped):
        return False, "missing RETURN clause"

    return True, ""


def _ensure_limit(cypher: str) -> str:
    stripped = _strip_cypher_comments(cypher)
    if not _LIMIT_PATTERN.search(stripped):
        return cypher.rstrip().rstrip(";") + f" LIMIT {_DEFAULT_LIMIT}"
    return cypher


def _is_statement_error(exc: Exception) -> bool:
    if not isinstance(exc, ClientError):
        return False
    code = getattr(exc, "code", "") or ""
    return code.startswith("Neo.ClientError.Statement.")


def _build_cypher_repair_prompt(
    *,
    schema: str,
    question: str,
    cypher: str,
    issue: str,
) -> str:
    return (
        "You are a Cypher query generator for a Neo4j algorithm knowledge graph.\n\n"
        "## Graph Schema\n"
        f"{schema}\n\n"
        "## Task\n"
        "Fix the Cypher query so it is valid and answers the question. "
        "The query MUST be read-only.\n"
        "Return ONLY the Cypher query, no explanation.\n\n"
        "## Allowed Cypher clauses\n"
        "MATCH, OPTIONAL MATCH, WHERE, WITH, RETURN, ORDER BY, LIMIT, UNWIND, collect, count, DISTINCT, AS, CASE, WHEN, THEN, ELSE, END\n\n"
        "## Forbidden\n"
        "Never use CREATE, MERGE, DELETE, DETACH, SET, REMOVE, DROP, CALL, LOAD CSV, FOREACH, or any apoc.* procedure.\n\n"
        "## Question\n"
        f"{question}\n\n"
        "## Current Cypher (broken)\n"
        f"{cypher}\n\n"
        "## Issue\n"
        f"{issue}\n"
    )

# Schema description injected into the Cypher generation prompt
_GRAPH_SCHEMA = f"""
Node labels: Entity, {", ".join(sorted(ENTITY_TYPE_LABELS))}, User
Entity nodes use a dual-label scheme: every entity has the base :Entity label, and known types also carry a type-specific label (e.g. :Entity:Algorithm). Some entities (e.g. those created by user profiling) may only have :Entity.
Entity properties: entity_id (string, unique), name (string), type (string, e.g. Algorithm/DataStructure/Concept/Problem/Technique), description (string), aliases (list of strings — abbreviations and alternative names, e.g. ["BFS", "广度优先搜索"])
User properties: entity_id (string, unique), user_id (string)

Relationship types:
  PREREQ        — source needs target as a learning prerequisite
  VARIANT_OF    — source is a specialisation / variant of target
  IMPROVES      — source improves target in time/space complexity or applicability
  USES          — source uses target as an implementation component
  APPLIES_TO    — solver → problem (always this direction)
  BELONGS_TO    — source belongs to target category / family
  RELATED_TO    — general relationship (fallback)
  MASTERED      — user has mastered (properties: confidence, evidence, last_updated)
  WEAK_AT       — user is weak at (properties: confidence, evidence, last_updated)
  INTERESTED_IN — user is interested in (properties: confidence, evidence, last_updated)

Preferred query patterns:
  By type label (faster, uses index): MATCH (e:Algorithm) WHERE ...
  By type property (works for all entities): MATCH (e:Entity) WHERE e.type = "Algorithm"

To find an entity by any name variant (including abbreviations like "BFS" or Chinese names like "广度优先搜索"):
  MATCH (e:Entity) WHERE toLower(e.name) = toLower("Breadth-First Search") OR ANY(a IN coalesce(e.aliases, []) WHERE toLower(a) = toLower("BFS"))
""".strip()


def create_graph_query(store: BaseGraphStore) -> BaseTool:
    """Factory: create a graph_query tool bound to *store* via closure."""

    @tool
    async def graph_query(question: str) -> str:
        """Query the algorithm knowledge graph using natural language.

        The question is converted to a Cypher query, executed against Neo4j,
        and the results are formatted as text.

        Args:
            question: Natural language question about algorithm relationships.

        Returns:
            Formatted query results or an error message.
        """
        # Step 1: LLM generates Cypher from natural language
        llm = ChatOpenAI(
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            temperature=0,
        )

        prompt = CYPHER_GENERATION_PROMPT.format(
            schema=_GRAPH_SCHEMA, question=question
        )
        response = await llm.ainvoke(prompt)
        candidate = response.content.strip()

        def _postprocess(raw: str) -> tuple[str, str | None]:
            cypher0 = _normalize_cypher(raw)
            ok, issue = _validate_read_cypher(cypher0)
            if not ok:
                return cypher0, issue
            return _ensure_limit(cypher0), None

        cypher, issue = _postprocess(candidate)
        if issue is not None:
            logger.warning("Generated invalid Cypher (%s): %s", issue, cypher)
            repair_prompt = _build_cypher_repair_prompt(
                schema=_GRAPH_SCHEMA,
                question=question,
                cypher=cypher,
                issue=issue,
            )
            repair = await llm.ainvoke(repair_prompt)
            cypher, issue = _postprocess(repair.content.strip())
            if issue is not None:
                if issue == "unsafe keyword detected":
                    logger.warning("Blocked unsafe Cypher after repair: %s", cypher)
                    return "Query rejected: only read operations are allowed."
                logger.warning("Cypher repair still invalid (%s): %s", issue, cypher)
                return "Graph query failed. Please try rephrasing your question."

        logger.debug("Final Cypher: %s", cypher)

        # Step 4: Execute against Neo4j
        try:
            records = await store.query_cypher(cypher)
        except Exception as e:
            logger.warning("Cypher execution failed: %s", e)
            if not _is_statement_error(e):
                return "Graph query failed. Please try rephrasing your question."

            repair_prompt = _build_cypher_repair_prompt(
                schema=_GRAPH_SCHEMA,
                question=question,
                cypher=cypher,
                issue=f"{type(e).__name__}: {e}",
            )
            repair = await llm.ainvoke(repair_prompt)
            cypher2, issue2 = _postprocess(repair.content.strip())
            if issue2 is not None:
                if issue2 == "unsafe keyword detected":
                    logger.warning("Blocked unsafe Cypher after execution repair: %s", cypher2)
                    return "Query rejected: only read operations are allowed."
                logger.warning("Execution repair produced invalid Cypher (%s): %s", issue2, cypher2)
                return "Graph query failed. Please try rephrasing your question."

            logger.debug("Repaired Cypher: %s", cypher2)
            try:
                records = await store.query_cypher(cypher2)
            except Exception as e2:
                logger.warning("Cypher execution failed after repair: %s", e2)
                return "Graph query failed. Please try rephrasing your question."

        if not records:
            return "No results found in the knowledge graph."

        # Step 5: Format results
        parts: list[str] = []
        for i, rec in enumerate(records[:20], 1):
            items = ", ".join(f"{k}: {v}" for k, v in rec.items())
            parts.append(f"[{i}] {items}")

        return "\n".join(parts)

    return graph_query
