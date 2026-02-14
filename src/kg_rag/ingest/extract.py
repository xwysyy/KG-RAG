"""LLM-based entity and relation extraction from text chunks."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections import Counter

import openai
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from kg_rag.config import settings
from kg_rag.models import Entity, Relation, TextChunk, make_entity_id
from kg_rag.utils import strip_code_fences

logger = logging.getLogger(__name__)

# Retry LLM calls on transient network / rate-limit errors
_retry_llm = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    retry=retry_if_exception_type((
        TimeoutError, ConnectionError, OSError,
        openai.RateLimitError, openai.APITimeoutError, openai.APIConnectionError,
    )),
    reraise=True,
)

_EXTRACTION_PROMPT = f"""\
You are an algorithm knowledge extraction expert for competitive programming \
(OI / ICPC). Given the text below, extract **entities** and **relations**.

## Output Format
Return a JSON object with two keys:
- "entities": array of {{{{"name": str, "type": str, "description": str, "aliases": [str]}}}}
- "relations": array of {{{{"source": str, "target": str, "type": str, "description": str}}}}

## Entity Types (use EXACTLY one per entity)
- Algorithm  — a named, deterministic computational procedure with well-defined steps \
(e.g. Dijkstra's Algorithm, Merge Sort). If it has a unique fixed procedure → Algorithm.
- DataStructure — a named, reusable data organisation with defined operations and \
complexity guarantees (e.g. Binary Heap, Segment Tree). Do NOT include implementation \
details like "Visited Array" or "Direction Vectors".
- Technique — a reusable problem-solving pattern or strategy that is NOT a single fixed \
procedure (e.g. Divide and Conquer, Two Pointers). Generic strategy → Technique; \
specific procedure → Algorithm.
- Problem — a concrete contest problem or a well-known problem class. \
Concrete problems: "Luogu PXXXX ProblemName". Problem classes: standard English name \
(e.g. "Shortest Path Problem").
- Concept — a theoretical notion, mathematical property, or complexity measure that \
does NOT fit the four types above (e.g. Time Complexity, Graph Connectivity). \
This is the residual category; always prefer the other four types first.

## Relation Types (use EXACTLY one per relation)
- PREREQ      — source needs target as a prerequisite (A* → Dijkstra's Algorithm)
- VARIANT_OF  — source is a specialisation / variant of target (Bidirectional BFS → BFS)
- IMPROVES    — source improves target in time/space/applicability (A* → Dijkstra's Algorithm)
- USES        — source uses target as an implementation component (BFS → Queue)
- APPLIES_TO  — solver → problem, ALWAYS this direction (BFS → Shortest Path Problem)
- BELONGS_TO  — source belongs to target category/family (BFS → Graph Traversal)
- RELATED_TO  — fallback only when none of the above fits

## Quality Rules
1. Only extract entities a student would look up as an independent topic on OI-Wiki.
2. Do NOT extract implementation details (loop variables, temporary arrays, direction vectors).
3. Prefer specific over vague: if both "Breadth-First Search" and "Search" appear, \
extract only "Breadth-First Search".
4. Every relation must carry clear, non-trivial semantics — not mere co-occurrence.
5. APPLIES_TO direction is ALWAYS Algorithm/Technique → Problem, never reversed.
6. Every relation source/target MUST be copied verbatim from an entity's "name" field \
(never use aliases or abbreviations). Every relation endpoint must appear in the entities list.

## Naming Rules
- Use the FULL ENGLISH name as entity name (e.g. "Breadth-First Search" not "BFS").
- Chinese names → translate to the standard English name \
(e.g. "广度优先搜索" → "Breadth-First Search").
- For concepts with no standard English name, use the most common Chinese name.
- Put abbreviations and alternative names in "aliases" \
(e.g. aliases: ["BFS", "广度优先搜索"]).
- For OI/competitive programming problems, use format: "Luogu PXXXX ProblemName".
- Be consistent: same concept → same name throughout.

Return ONLY valid JSON, no explanation.

## Text
{{text}}
"""


@_retry_llm
async def _extract_one_chunk(
    chunk: TextChunk,
    llm: ChatOpenAI,
    sem: asyncio.Semaphore,
) -> tuple[list[Entity], list[Relation]]:
    """Extract entities and relations from a single chunk (with semaphore)."""
    async with sem:
        prompt = _EXTRACTION_PROMPT.format(text=chunk.content)
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        raw = response.content.strip()

        entities, relations = _parse_extraction(raw, chunk.id)

        # Retry once if parsing failed
        if not entities and not relations:
            logger.info("Retrying extraction for chunk %s", chunk.id)
            retry_resp = await llm.ainvoke(
                [HumanMessage(content=prompt + "\n\nReturn ONLY valid JSON, no extra text.")]
            )
            entities, relations = _parse_extraction(
                retry_resp.content.strip(), chunk.id
            )

        return entities, relations


def merge_entities(entity_lists: list[list[Entity]]) -> list[Entity]:
    """Merge entities from multiple chunks by lowercase name key.

    - description: line-level dedup concatenation
    - type: majority vote
    - aliases: collect name variants + LLM-provided aliases
    - source_chunks: union
    """
    all_entities: dict[str, Entity] = {}
    type_counter: dict[str, Counter] = {}

    for entities in entity_lists:
        for ent in entities:
            key = ent.name.lower()
            if key in all_entities:
                existing = all_entities[key]
                existing.source_chunks.extend(
                    cid for cid in ent.source_chunks
                    if cid not in existing.source_chunks
                )
                # description: line-level dedup
                if ent.description:
                    existing_lines = set(existing.description.splitlines())
                    new_lines = [
                        ln for ln in ent.description.splitlines()
                        if ln not in existing_lines
                    ]
                    if new_lines:
                        existing.description = (
                            existing.description + "\n" + "\n".join(new_lines)
                        ).strip()
                # collect name variants as aliases
                if ent.name != existing.name and ent.name not in existing.aliases:
                    existing.aliases.append(ent.name)
                # merge LLM-provided aliases
                for alias in ent.aliases:
                    if alias not in existing.aliases and alias != existing.name:
                        existing.aliases.append(alias)
                type_counter[key][ent.type] += 1
            else:
                all_entities[key] = ent
                type_counter[key] = Counter({ent.type: 1})

    # type: majority vote
    for key, ent in all_entities.items():
        ent.type = type_counter[key].most_common(1)[0][0]

    return list(all_entities.values())


def dedup_by_alias_cross_ref(
    entities: list[Entity],
) -> tuple[list[Entity], dict[str, str]]:
    """Merge entities whose name/alias sets overlap (Union-Find).

    Returns (merged_entities, name_map) where name_map maps
    old entity names to their canonical name after merging.
    """
    if not entities:
        return entities, {}

    n = len(entities)

    # Union-Find
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    # Build name→index and alias→indices mappings (name↔alias only, no alias↔alias)
    MIN_TOKEN_LEN = 2
    name_to_idx: dict[str, int] = {}
    alias_to_indices: dict[str, list[int]] = {}

    for i, ent in enumerate(entities):
        name_lower = ent.name.strip().lower()
        if len(name_lower) >= MIN_TOKEN_LEN:
            name_to_idx[name_lower] = i
        for alias in ent.aliases:
            tok = alias.strip().lower()
            if len(tok) >= MIN_TOKEN_LEN:
                alias_to_indices.setdefault(tok, []).append(i)

    # Union: entity A's name matches entity B's alias (or vice versa)
    for name_tok, name_idx in name_to_idx.items():
        for alias_idx in alias_to_indices.get(name_tok, []):
            if alias_idx != name_idx:
                union(name_idx, alias_idx)

    # Group entities by root
    groups: dict[int, list[Entity]] = {}
    for i, ent in enumerate(entities):
        root = find(i)
        groups.setdefault(root, []).append(ent)

    # Merge each group and build name_map
    merged: list[Entity] = []
    name_map: dict[str, str] = {}
    for group in groups.values():
        if len(group) == 1:
            merged.append(group[0])
            continue
        # Pick canonical name: longest name in the group (most descriptive)
        canonical_name = max((ent.name for ent in group), key=len)
        # Collect original names that differ from canonical — these become aliases
        original_names = [
            ent.name for ent in group if ent.name != canonical_name
        ]
        # Normalize all entities to the canonical name so merge_entities
        # groups them under one key
        normalized = [
            ent.model_copy(update={"name": canonical_name}) for ent in group
        ]
        result = merge_entities([normalized])
        if len(result) != 1:
            logger.warning(
                "Alias cross-ref merge produced %d entities for group %r, expected 1",
                len(result), canonical_name,
            )
            merged.extend(result)
            continue
        canonical_ent = result[0]
        # Ensure original names are preserved as aliases
        for orig_name in original_names:
            if orig_name not in canonical_ent.aliases:
                canonical_ent.aliases.append(orig_name)
        # Recompute ID to match canonical name
        canonical_ent.id = make_entity_id(canonical_name)
        merged.append(canonical_ent)
        # Map all original names to canonical name
        for ent in group:
            if ent.name != canonical_name:
                name_map[ent.name] = canonical_name

    return merged, name_map


_DEDUP_PROMPT = """\
You are a knowledge-graph deduplication expert.
Below is a numbered list of entities (name + aliases). Identify groups of
entities that refer to the SAME concept (different surface forms of one thing).

Rules:
- Only merge entities that are genuinely the same concept expressed differently.
- Do NOT merge entities that are merely related (e.g. "BFS" and "Queue").
- "canonical" must be one of the existing entity names listed below.

## Entities
{entity_list}

## Output Format
Return ONLY a JSON object:
{{"groups": [{{"canonical": "<existing entity name>", "duplicates": ["<name>", ...]}}]}}

If no duplicates found, return: {{"groups": []}}
"""


async def dedup_by_llm(
    entities: list[Entity],
    llm: ChatOpenAI,
) -> tuple[list[Entity], dict[str, str]]:
    """Ask LLM to identify duplicate entity groups (one call)."""
    if len(entities) < 2:
        return entities, {}

    # Build numbered entity list for prompt
    lines = []
    name_set = {ent.name for ent in entities}
    for i, ent in enumerate(entities, 1):
        alias_str = ", ".join(ent.aliases) if ent.aliases else "(none)"
        lines.append(f"{i}. {ent.name}  [aliases: {alias_str}]")
    entity_list = "\n".join(lines)

    prompt = _DEDUP_PROMPT.format(entity_list=entity_list)
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    raw = response.content.strip()

    data = _extract_json_object(raw)
    if data is None:
        logger.warning("Failed to parse dedup LLM response, skipping LLM dedup")
        return entities, {}
    if not isinstance(data, dict):
        logger.warning("dedup LLM returned non-dict JSON, skipping")
        return entities, {}

    groups = data.get("groups", [])
    if not groups:
        return entities, {}

    # Build name_map from LLM groups (with type validation)
    name_map: dict[str, str] = {}
    for group in groups:
        if not isinstance(group, dict):
            continue
        canonical = group.get("canonical", "")
        duplicates = group.get("duplicates", [])
        if not isinstance(canonical, str) or not canonical or canonical not in name_set:
            logger.warning("LLM dedup: canonical %r not found, skipping group", canonical)
            continue
        if not isinstance(duplicates, list):
            continue
        for dup in duplicates:
            if not isinstance(dup, str):
                continue
            if dup in name_set and dup != canonical:
                name_map[dup] = canonical

    if not name_map:
        return entities, {}

    # Merge duplicates into their canonical entities
    # Normalize dup name → canonical name before merging so merge_entities works
    ent_by_name: dict[str, Entity] = {ent.name: ent for ent in entities}
    for dup_name, canon_name in name_map.items():
        if dup_name not in ent_by_name or canon_name not in ent_by_name:
            continue
        dup_ent = ent_by_name.pop(dup_name)
        canon_ent = ent_by_name[canon_name]
        # Normalize dup to canonical name so merge_entities groups them
        dup_normalized = dup_ent.model_copy(update={"name": canon_name})
        result = merge_entities([[canon_ent, dup_normalized]])
        merged_ent = result[0]
        # Preserve original dup name as alias
        if dup_name not in merged_ent.aliases:
            merged_ent.aliases.append(dup_name)
        # Recompute ID to match canonical name
        merged_ent.id = make_entity_id(canon_name)
        ent_by_name[canon_name] = merged_ent

    return list(ent_by_name.values()), name_map


def _resolve_name(name: str, name_map: dict[str, str]) -> str:
    """Follow name_map transitively to the final canonical name."""
    seen: set[str] = set()
    while name in name_map and name not in seen:
        seen.add(name)
        name = name_map[name]
    return name


def remap_relations(
    relations: list[Relation],
    name_map: dict[str, str],
) -> list[Relation]:
    """Remap relation endpoints using name_map and deduplicate."""
    result: list[Relation] = []
    seen: set[tuple[str, str, str]] = set()
    for rel in relations:
        src = _resolve_name(rel.source, name_map)
        tgt = _resolve_name(rel.target, name_map)
        if src == tgt:
            continue
        key = (src, tgt, rel.type)
        if key in seen:
            continue
        seen.add(key)
        result.append(
            Relation(
                source=src, target=tgt, type=rel.type,
                description=rel.description, weight=rel.weight,
            )
        )
    return result


async def extract_entities_and_relations(
    chunks: list[TextChunk],
    *,
    sem: asyncio.Semaphore | None = None,
    llm: ChatOpenAI | None = None,
) -> tuple[list[Entity], list[Relation]]:
    """Extract entities and relations from a list of text chunks via LLM.

    Uses up to ``settings.llm_concurrency`` parallel LLM calls.
    Accepts optional shared *sem* and *llm* for batch mode; creates its own
    when not provided (single-file backward compat).
    """
    if llm is None:
        llm = ChatOpenAI(
            model=settings.reasoning_llm_model,
            api_key=settings.reasoning_llm_api_key,
            base_url=settings.reasoning_llm_base_url,
            temperature=0,
        )
    if sem is None:
        sem = asyncio.Semaphore(settings.llm_concurrency)

    results = await asyncio.gather(
        *(_extract_one_chunk(chunk, llm, sem) for chunk in chunks),
        return_exceptions=True,
    )
    # Filter out failed chunks
    failed = [(chunks[i], r) for i, r in enumerate(results) if isinstance(r, Exception)]
    for chunk, exc in failed:
        logger.error("Chunk %s extraction failed: %s", chunk.id, exc)
    results = [r for r in results if not isinstance(r, Exception)]

    all_entity_lists = [ents for ents, _ in results]
    merged = merge_entities(all_entity_lists)

    all_relations: list[Relation] = []
    for _, relations in results:
        all_relations.extend(relations)

    # Layer 1: alias cross-reference dedup (always, zero LLM cost)
    merged, name_map = dedup_by_alias_cross_ref(merged)
    logger.info(
        "After alias cross-ref dedup: %d entities (%d merged)",
        len(merged), len(name_map),
    )

    # Layer 2: LLM dedup (one extra call)
    merged, name_map_llm = await dedup_by_llm(merged, llm)
    name_map.update(name_map_llm)
    logger.info(
        "After LLM dedup: %d entities (%d merged by LLM)",
        len(merged), len(name_map_llm),
    )

    # Remap relations with combined name_map
    all_relations = remap_relations(all_relations, name_map)

    logger.info(
        "Extracted %d entities, %d relations from %d chunks",
        len(merged), len(all_relations), len(chunks),
    )
    return merged, all_relations


def _extract_json_object(raw: str) -> dict | None:
    """Try to extract the outermost JSON object from raw text."""
    # Strip <think>...</think> reasoning tags (deepseek-reasoner)
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", raw).strip()
    cleaned = strip_code_fences(cleaned)

    # Try direct parse first
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Regex fallback: find outermost { ... }
    m = re.search(r"\{[\s\S]*\}", cleaned)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass

    return None


def _parse_extraction(
    raw: str, chunk_id: str
) -> tuple[list[Entity], list[Relation]]:
    """Parse LLM JSON output into Entity and Relation lists."""

    entities: list[Entity] = []
    relations: list[Relation] = []

    data = _extract_json_object(raw)
    if data is None:
        logger.warning("Failed to parse extraction JSON from chunk %s", chunk_id)
        return entities, relations
    if not isinstance(data, dict):
        logger.warning("Extraction returned non-dict JSON for chunk %s", chunk_id)
        return entities, relations

    for e in data.get("entities", []):
        if not isinstance(e, dict):
            continue
        name = e.get("name", "").strip()
        if not name:
            continue
        raw_aliases = e.get("aliases") or []
        aliases = [a for a in raw_aliases if isinstance(a, str) and a.strip()]
        entities.append(
            Entity(
                id=make_entity_id(name),
                name=name,
                type=e.get("type", "Concept"),
                description=e.get("description", ""),
                source_chunks=[chunk_id],
                aliases=aliases,
            )
        )

    for r in data.get("relations", []):
        if not isinstance(r, dict):
            continue
        src = r.get("source", "").strip()
        tgt = r.get("target", "").strip()
        if not src or not tgt:
            continue
        relations.append(
            Relation(
                source=src,
                target=tgt,
                type=r.get("type", "RELATED_TO"),
                description=r.get("description", ""),
            )
        )

    # Filter relations whose endpoints are not in the entity name set
    entity_names = {e.name for e in entities}
    valid_relations: list[Relation] = []
    for rel in relations:
        if rel.source not in entity_names or rel.target not in entity_names:
            logger.warning(
                "Dropping relation %s->%s (%s): endpoint not in entity set (chunk %s)",
                rel.source, rel.target, rel.type, chunk_id,
            )
            continue
        valid_relations.append(rel)

    return entities, valid_relations
