"""CLI entry point — supports ``chat`` and ``ingest`` subcommands.

Usage::

    python -m kg_rag chat
    python -m kg_rag ingest <file_path>
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from langchain_core.messages import HumanMessage

from kg_rag.config import settings
from kg_rag.models import KNOWLEDGE_REL_TYPES

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Initialization helpers
# ---------------------------------------------------------------------------

async def _preflight_checks() -> None:
    """Validate critical config before starting."""
    errors: list[str] = []

    if not settings.llm_api_key:
        errors.append("LLM_API_KEY is not set")

    # Test Neo4j connectivity
    from neo4j import AsyncGraphDatabase
    from neo4j.exceptions import ServiceUnavailable, AuthError

    driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_username, settings.neo4j_password),
    )
    try:
        async with driver.session(database=settings.neo4j_database) as session:
            await (await session.run("RETURN 1")).consume()
    except ServiceUnavailable:
        errors.append(f"Cannot connect to Neo4j at {settings.neo4j_uri}")
    except AuthError:
        errors.append("Neo4j authentication failed (check NEO4J_USERNAME/NEO4J_PASSWORD)")
    except Exception as e:
        errors.append(f"Neo4j error: {e}")
    finally:
        await driver.close()

    if not settings.embedding_api_key:
        errors.append("EMBEDDING_API_KEY is not set")
    if not settings.embedding_base_url:
        errors.append("EMBEDDING_BASE_URL is not set")

    if not settings.firecrawl_api_key:
        logger.warning("FIRECRAWL_API_KEY not set — web search will be disabled")

    if errors:
        for msg in errors:
            logger.error("Preflight check failed: %s", msg)
        sys.exit(1)

    logger.info("Preflight checks passed")


async def _init_stores():
    """Initialize storage backends and return (vector_store, graph_store)."""
    from kg_rag.storage.nano_vector import NanoVectorStore
    from kg_rag.storage.neo4j_graph import Neo4jGraphStore

    vector_store = NanoVectorStore()
    graph_store = Neo4jGraphStore()
    await graph_store.initialize()

    return vector_store, graph_store


async def _init_graph_only():
    """Initialize only the graph store (no vector/embedding deps)."""
    from kg_rag.storage.neo4j_graph import Neo4jGraphStore

    graph_store = Neo4jGraphStore()
    await graph_store.initialize()
    return graph_store


async def _preflight_graph_only() -> None:
    """Validate Neo4j connectivity only (no LLM key required)."""
    from neo4j import AsyncGraphDatabase
    from neo4j.exceptions import ServiceUnavailable, AuthError

    errors: list[str] = []
    driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_username, settings.neo4j_password),
    )
    try:
        async with driver.session(database=settings.neo4j_database) as session:
            await (await session.run("RETURN 1")).consume()
    except ServiceUnavailable:
        errors.append(f"Cannot connect to Neo4j at {settings.neo4j_uri}")
    except AuthError:
        errors.append("Neo4j authentication failed (check NEO4J_USERNAME/NEO4J_PASSWORD)")
    except Exception as e:
        errors.append(f"Neo4j error: {e}")
    finally:
        await driver.close()

    if errors:
        for msg in errors:
            logger.error("Preflight check failed: %s", msg)
        sys.exit(1)


def _build_tools(vector_store, graph_store):
    """Wire up stores into tool modules and return the tool list."""
    from kg_rag.tools.vector_search import create_vector_search
    from kg_rag.tools.graph_query import create_graph_query
    from kg_rag.tools.web_search import web_search

    return [
        create_vector_search(vector_store),
        create_graph_query(graph_store),
        web_search,
    ]


# ---------------------------------------------------------------------------
# Chat subcommand
# ---------------------------------------------------------------------------

async def _chat(user_id: str = "default") -> None:
    """Interactive chat loop."""
    from kg_rag.agent.graph import build_agent_graph
    from kg_rag.memory.profile import read_profile
    from kg_rag.memory.proposal import (
        apply_proposals,
        extract_proposals,
        filter_proposals,
    )

    await _preflight_checks()
    vector_store, graph_store = await _init_stores()
    tools = _build_tools(vector_store, graph_store)
    agent = build_agent_graph(tools)

    print("算法知识问答系统 (输入 quit 退出)")
    print("-" * 40)

    conversation_log: list[str] = []

    try:
        while True:
            try:
                question = input("\n> ").strip()
            except EOFError:
                break
            if not question or question.lower() in ("quit", "exit", "q"):
                break

            # Read user profile
            profile = await read_profile(user_id, graph_store)

            # Run agent graph
            result = await agent.ainvoke(
                {
                    "messages": [HumanMessage(content=question)],
                    "todos": [],
                    "user_profile": profile,
                    "iteration": 0,
                    "max_iterations": settings.max_iterations,
                    "intermediate_results": [],
                    "final_answer": "",
                    "files": {},
                }
            )

            answer = result.get("final_answer", "No answer produced.")
            print(f"\n{answer}")

            # Accumulate conversation for profile extraction
            conversation_log.append(f"User: {question}")
            conversation_log.append(f"Assistant: {answer}")

    finally:
        # Post-conversation: extract and apply profile updates
        try:
            if conversation_log:
                logger.info("Extracting profile proposals...")
                conv_text = "\n".join(conversation_log)
                proposals = await extract_proposals(conv_text, user_id)
                accepted = filter_proposals(proposals)
                if accepted:
                    await apply_proposals(accepted, graph_store)
        except Exception as e:
            logger.warning("Profile extraction failed: %s", e)
        finally:
            await graph_store.finalize()
            await vector_store.finalize()


# ---------------------------------------------------------------------------
# Ingest subcommand
# ---------------------------------------------------------------------------

async def _ingest(file_path: str) -> None:
    """Ingest a text file: chunk → extract entities/relations → store."""
    from kg_rag.ingest.chunking import chunk_by_tokens
    from kg_rag.ingest.extract import extract_entities_and_relations
    from kg_rag.models import make_entity_id

    await _preflight_checks()

    path = Path(file_path)
    if not path.exists():
        print(f"File not found: {path}")
        sys.exit(1)

    text = path.read_text(encoding="utf-8")
    doc_id = path.stem
    print(f"Ingesting {path.name} ({len(text)} chars)...")

    # Step 1: chunk
    chunks = chunk_by_tokens(text, doc_id=doc_id)
    print(f"  → {len(chunks)} chunks")

    # Step 2: extract entities & relations
    entities, relations, failed_chunks = await extract_entities_and_relations(chunks)
    print(f"  → {len(entities)} entities, {len(relations)} relations")
    if failed_chunks:
        print(f"  ⚠ {len(failed_chunks)} chunks failed extraction:")
        for fc in failed_chunks:
            print(f"    - {fc['chunk_id']}: {fc['error']}")

    # Step 3: store
    vector_store, graph_store = await _init_stores()

    try:
        # Upsert chunks into vector store
        chunk_data = {
            c.id: {"content": c.content, "doc_id": c.doc_id, **c.metadata} for c in chunks
        }
        try:
            await vector_store.upsert(chunk_data)
            print(f"  → {len(chunks)} chunks stored in vector DB")
        except Exception as e:
            logger.warning("Vector upsert failed: %s", e)

        # Upsert entities into graph store (concurrent)
        sem = asyncio.Semaphore(settings.storage_concurrency)

        async def _upsert_node(ent):
            async with sem:
                await graph_store.upsert_node(
                    ent.id,
                    {
                        "label": ent.type,
                        "name": ent.name,
                        "description": ent.description,
                        "aliases": ent.aliases,
                    },
                )

        results = await asyncio.gather(*(_upsert_node(ent) for ent in entities), return_exceptions=True)
        node_errors = [r for r in results if isinstance(r, Exception)]
        if node_errors:
            logger.error("Failed to upsert %d/%d nodes", len(node_errors), len(entities))

        # Upsert relations into graph store (concurrent)
        async def _upsert_edge(rel):
            async with sem:
                if rel.type not in KNOWLEDGE_REL_TYPES:
                    logger.warning(
                        "LLM produced unknown relation type %r (%s->%s), "
                        "storage layer will remap",
                        rel.type, rel.source, rel.target,
                    )
                src_id = make_entity_id(rel.source)
                tgt_id = make_entity_id(rel.target)
                await graph_store.upsert_edge(
                    src_id,
                    tgt_id,
                    {
                        "type": rel.type,
                        "description": rel.description,
                        "weight": rel.weight,
                    },
                )

        results = await asyncio.gather(*(_upsert_edge(rel) for rel in relations), return_exceptions=True)
        edge_errors = [r for r in results if isinstance(r, Exception)]
        if edge_errors:
            logger.error("Failed to upsert %d/%d edges", len(edge_errors), len(relations))

        print(f"  → {len(entities)} nodes, {len(relations)} edges stored in Neo4j")
        print("Done.")

    finally:
        await graph_store.finalize()
        await vector_store.finalize()


# ---------------------------------------------------------------------------
# Batch ingest subcommand
# ---------------------------------------------------------------------------

async def _ingest_batch(dir_path: str) -> None:
    """Ingest all .md files under *dir_path* with globally shared concurrency."""
    from kg_rag.ingest.chunking import chunk_by_tokens
    from kg_rag.ingest.extract import extract_entities_and_relations
    from kg_rag.models import make_entity_id
    from langchain_openai import ChatOpenAI

    await _preflight_checks()

    root = Path(dir_path)
    if not root.is_dir():
        print(f"Directory not found: {root}")
        sys.exit(1)

    md_files = sorted(root.glob("*.md"))
    if not md_files:
        print(f"No .md files found in {root}")
        sys.exit(1)

    print(f"Found {len(md_files)} .md files in {root}")

    # Shared resources
    llm = ChatOpenAI(
        model=settings.reasoning_llm_model,
        api_key=settings.reasoning_llm_api_key,
        base_url=settings.reasoning_llm_base_url,
        temperature=0,
        request_timeout=settings.llm_request_timeout,
    )
    llm_sem = asyncio.Semaphore(settings.llm_concurrency)
    storage_sem = asyncio.Semaphore(settings.storage_concurrency)
    file_sem = asyncio.Semaphore(settings.file_concurrency)
    vector_store, graph_store = await _init_stores()
    total = len(md_files)
    done_count = [0]  # mutable counter for nested scope

    async def _process_one_file(path: Path) -> None:
        async with file_sem:
            text = path.read_text(encoding="utf-8")
            doc_id = path.stem
            logger.info("Ingesting %s (%d chars)", path.name, len(text))

            # chunk
            chunks = chunk_by_tokens(text, doc_id=doc_id)
            logger.info("  %s → %d chunks", path.name, len(chunks))

            # extract (shared llm & llm_sem)
            entities, relations, failed_chunks = await extract_entities_and_relations(
                chunks, sem=llm_sem, llm=llm,
            )
            logger.info(
                "  %s → %d entities, %d relations",
                path.name, len(entities), len(relations),
            )
            if failed_chunks:
                logger.warning(
                    "  %s: %d chunks failed extraction: %s",
                    path.name, len(failed_chunks),
                    ", ".join(fc["chunk_id"] for fc in failed_chunks),
                )

            # store chunks (non-blocking: vector failure must not prevent graph writes)
            chunk_data = {
                c.id: {"content": c.content, "doc_id": c.doc_id, **c.metadata} for c in chunks
            }
            try:
                await vector_store.upsert(chunk_data)
            except Exception as e:
                logger.warning("%s: vector upsert failed: %s", path.name, e)

            # store entities (shared storage_sem)
            async def _upsert_node(ent):
                async with storage_sem:
                    await graph_store.upsert_node(
                        ent.id,
                        {
                            "label": ent.type,
                            "name": ent.name,
                            "description": ent.description,
                            "aliases": ent.aliases,
                        },
                    )

            results = await asyncio.gather(
                *(_upsert_node(ent) for ent in entities), return_exceptions=True,
            )
            node_errors = [r for r in results if isinstance(r, Exception)]
            if node_errors:
                logger.error(
                    "%s: failed to upsert %d/%d nodes",
                    path.name, len(node_errors), len(entities),
                )

            # store relations (shared storage_sem)
            async def _upsert_edge(rel):
                async with storage_sem:
                    if rel.type not in KNOWLEDGE_REL_TYPES:
                        logger.warning(
                            "LLM produced unknown relation type %r (%s->%s), "
                            "storage layer will remap",
                            rel.type, rel.source, rel.target,
                        )
                    src_id = make_entity_id(rel.source)
                    tgt_id = make_entity_id(rel.target)
                    await graph_store.upsert_edge(
                        src_id, tgt_id,
                        {
                            "type": rel.type,
                            "description": rel.description,
                            "weight": rel.weight,
                        },
                    )

            results = await asyncio.gather(
                *(_upsert_edge(rel) for rel in relations), return_exceptions=True,
            )
            edge_errors = [r for r in results if isinstance(r, Exception)]
            if edge_errors:
                logger.error(
                    "%s: failed to upsert %d/%d edges",
                    path.name, len(edge_errors), len(relations),
                )

            done_count[0] += 1
            print(
                f"  [{done_count[0]}/{total}] {path.name}: {len(entities)} entities, "
                f"{len(relations)} relations, {len(chunks)} chunks"
            )

    try:
        results = await asyncio.gather(
            *(_process_one_file(p) for p in md_files),
            return_exceptions=True,
        )
        failed = [(md_files[i], r) for i, r in enumerate(results) if isinstance(r, Exception)]
        for path, exc in failed:
            logger.error("Failed to ingest %s: %s", path.name, exc)
        print(f"All {len(md_files)} files ingested ({len(failed)} failed).")
    finally:
        await graph_store.finalize()
        await vector_store.finalize()


# ---------------------------------------------------------------------------
# Vector metadata maintenance
# ---------------------------------------------------------------------------

async def _vector_retag(dir_path: str, *, dry_run: bool = False) -> None:
    """Backfill missing ``doc_id`` in the NanoVectorDB storage file.

    The initial vector DB may have been created before we stored provenance.
    Since chunk IDs are deterministic (doc_id + index → sha256), we can
    re-chunk the source docs to reconstruct a mapping chunk_id → doc_id and
    then attach it to existing vector records without re-embedding.
    """
    from kg_rag.ingest.chunking import chunk_by_tokens

    root = Path(dir_path)
    if not root.is_dir():
        print(f"Directory not found: {root}")
        sys.exit(1)

    md_files = sorted(root.rglob("*.md"))
    if not md_files:
        print(f"No .md files found in {root}")
        sys.exit(1)

    vector_path = settings.data_dir / "nano_vector.json"
    if not vector_path.exists():
        print(f"Vector DB not found: {vector_path}")
        sys.exit(1)

    print(f"Loading vector DB: {vector_path}")
    db = json.loads(vector_path.read_text(encoding="utf-8"))
    records = db.get("data") or []
    if not isinstance(records, list):
        print("Vector DB format error: 'data' is not a list")
        sys.exit(1)

    print(f"Building chunk_id → doc_id map from {len(md_files)} markdown files...")
    id_to_doc: dict[str, str] = {}
    for path in md_files:
        text = path.read_text(encoding="utf-8")
        doc_id = path.stem
        chunks = chunk_by_tokens(text, doc_id=doc_id)
        for c in chunks:
            id_to_doc[c.id] = doc_id

    updated = 0
    already = 0
    missing = 0
    for rec in records:
        if rec.get("doc_id"):
            already += 1
            continue
        cid = rec.get("__id__", "")
        doc_id = id_to_doc.get(cid)
        if doc_id:
            rec["doc_id"] = doc_id
            updated += 1
        else:
            missing += 1

    print(
        f"doc_id present: {already}, backfilled: {updated}, still missing: {missing} "
        f"(total records: {len(records)})"
    )

    if dry_run:
        print("Dry run — no changes written.")
        return

    print("Writing updated vector DB...")
    vector_path.write_text(
        json.dumps(db, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print("Done.")


# ---------------------------------------------------------------------------
# Merge subcommand
# ---------------------------------------------------------------------------

async def _merge(source_names: list[str], target_name: str) -> None:
    """Merge source entities into the target entity in Neo4j."""
    from kg_rag.models import make_entity_id

    await _preflight_graph_only()
    graph_store = await _init_graph_only()

    target_id = make_entity_id(target_name)

    try:
        # Verify target exists
        rows = await graph_store.query_cypher(
            "MATCH (n:Entity {entity_id: $eid}) RETURN n.name AS name",
            {"eid": target_id},
        )
        if not rows:
            print(f"Target entity '{target_name}' not found in graph.")
            sys.exit(1)

        for src_name in source_names:
            src_id = make_entity_id(src_name)
            if src_id == target_id:
                print(f"  Skipping '{src_name}' (same as target)")
                continue

            src_rows = await graph_store.query_cypher(
                "MATCH (n:Entity {entity_id: $eid}) "
                "RETURN n.name AS name, n.description AS description, "
                "n.aliases AS aliases",
                {"eid": src_id},
            )
            if not src_rows:
                print(f"  Source entity '{src_name}' not found, skipping")
                continue

            # Collect outgoing edges from source (excluding edges to target)
            out_edges = await graph_store.query_cypher(
                "MATCH (s:Entity {entity_id: $sid})-[r]->(t:Entity) "
                "RETURN t.entity_id AS tid, type(r) AS rtype, "
                "properties(r) AS props",
                {"sid": src_id},
            )
            # Collect incoming edges to source (excluding edges from target)
            in_edges = await graph_store.query_cypher(
                "MATCH (t:Entity)-[r]->(s:Entity {entity_id: $sid}) "
                "RETURN t.entity_id AS tid, type(r) AS rtype, "
                "properties(r) AS props",
                {"sid": src_id},
            )

            # Redirect outgoing edges preserving relationship type
            for edge in out_edges:
                neighbor_id = edge["tid"]
                if neighbor_id == target_id:
                    logger.info(
                        "Dropping source→target edge (%s)-[%s]->(%s)",
                        src_name, edge["rtype"], target_name,
                    )
                    continue
                props = dict(edge.get("props") or {})
                props["type"] = edge["rtype"]
                await graph_store.upsert_edge(target_id, neighbor_id, props)

            # Redirect incoming edges preserving relationship type
            for edge in in_edges:
                neighbor_id = edge["tid"]
                if neighbor_id == target_id:
                    logger.info(
                        "Dropping target→source edge (%s)-[%s]->(%s)",
                        target_name, edge["rtype"], src_name,
                    )
                    continue
                props = dict(edge.get("props") or {})
                props["type"] = edge["rtype"]
                await graph_store.upsert_edge(neighbor_id, target_id, props)

            # Merge description and aliases into target
            src_desc = src_rows[0].get("description", "") or ""
            src_aliases = src_rows[0].get("aliases") or []
            stored_name = src_rows[0].get("name", "") or ""
            # Include both CLI arg and stored canonical name
            new_aliases = list({stored_name, src_name} - {""}) + src_aliases

            await graph_store.query_cypher(
                "MATCH (n:Entity {entity_id: $tid}) "
                "SET n.description = CASE "
                "  WHEN n.description IS NULL OR n.description = '' "
                "    THEN $desc "
                "  WHEN $desc = '' THEN n.description "
                "  ELSE n.description + '\n' + $desc END, "
                "n.aliases = CASE "
                "  WHEN n.aliases IS NULL THEN $new_aliases "
                "  ELSE n.aliases + "
                "    [x IN $new_aliases WHERE NOT x IN n.aliases] END",
                {"tid": target_id, "desc": src_desc,
                 "new_aliases": new_aliases},
            )

            # Delete source node
            await graph_store.query_cypher(
                "MATCH (n:Entity {entity_id: $eid}) DETACH DELETE n",
                {"eid": src_id},
            )
            print(f"  Merged '{src_name}' → '{target_name}'")

        print("Done.")

    finally:
        await graph_store.finalize()

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="kg-rag",
        description="算法知识问答系统 — KG + RAG + Agentic",
    )
    sub = parser.add_subparsers(dest="command")

    # chat
    chat_p = sub.add_parser("chat", help="Interactive Q&A session")
    chat_p.add_argument(
        "--user", default="default", help="User ID for profile tracking"
    )

    # ingest
    ingest_p = sub.add_parser("ingest", help="Ingest a text document")
    ingest_p.add_argument("file", help="Path to the text file")

    # ingest-dir
    ingest_dir_p = sub.add_parser("ingest-dir", help="Batch ingest all .md files in a directory")
    ingest_dir_p.add_argument("dir", help="Path to the directory containing .md files")

    # vector-retag
    vec_p = sub.add_parser(
        "vector-retag",
        help="Backfill missing doc_id metadata in the vector DB (no re-embedding)",
    )
    vec_p.add_argument("dir", help="Directory containing the source .md files")
    vec_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Only report how many records would be updated",
    )

    # serve
    serve_p = sub.add_parser("serve", help="Run FastAPI backend server")
    serve_p.add_argument(
        "--host",
        default=settings.api_host,
        help=f"Host to bind (default: {settings.api_host})",
    )
    serve_p.add_argument(
        "--port",
        type=int,
        default=settings.api_port,
        help=f"Port to bind (default: {settings.api_port})",
    )

    # merge
    merge_p = sub.add_parser(
        "merge", help="Merge duplicate entities in the knowledge graph",
    )
    merge_p.add_argument(
        "--source", nargs="+", required=True,
        help="Source entity names to merge away",
    )
    merge_p.add_argument(
        "--target", required=True,
        help="Target entity name to merge into",
    )

    args = parser.parse_args()

    if args.command == "chat":
        asyncio.run(_chat(user_id=args.user))
    elif args.command == "ingest":
        asyncio.run(_ingest(args.file))
    elif args.command == "ingest-dir":
        asyncio.run(_ingest_batch(args.dir))
    elif args.command == "vector-retag":
        asyncio.run(_vector_retag(args.dir, dry_run=args.dry_run))
    elif args.command == "merge":
        asyncio.run(_merge(args.source, args.target))
    elif args.command == "serve":
        import uvicorn
        uvicorn.run(
            "kg_rag.asgi:app",
            host=args.host,
            port=args.port,
            reload=False,
        )
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
