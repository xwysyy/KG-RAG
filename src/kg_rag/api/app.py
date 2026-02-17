"""FastAPI application exposing session-based LangGraph chat APIs."""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from kg_rag.agent.graph import build_agent_graph
from kg_rag.api.auth import (
    create_access_token,
    get_current_user_id,
    hash_password,
    verify_password,
)
from kg_rag.api.schemas import (
    AuthResponse,
    ChatTurnResponse,
    GraphEdgeResponse,
    GraphNodeResponse,
    GraphOverviewResponse,
    GraphStatsResponse,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    SessionCreateRequest,
    SessionMessageCreateRequest,
    SessionMessagesResponse,
    SessionResponse,
    SessionSummaryResponse,
)
from kg_rag.models import ENTITY_TYPE_LABELS
from kg_rag.api.service import ChatService
from kg_rag.api.session_store import (
    MessageRecord,
    SessionRecord,
    SessionSummaryRecord,
    SqliteSessionStore,
)
from kg_rag.config import settings
from kg_rag.storage.nano_vector import NanoVectorStore
from kg_rag.storage.neo4j_graph import Neo4jGraphStore
from kg_rag.tools.graph_query import create_graph_query
from kg_rag.tools.vector_search import create_vector_search
from kg_rag.tools.web_search import web_search

logger = logging.getLogger(__name__)


def _message_response(record: MessageRecord) -> MessageResponse:
    return MessageResponse(
        message_id=record.message_id,
        session_id=record.session_id,
        role=record.role,
        content=record.content,
        created_at=record.created_at,
    )


def _session_response(record: SessionRecord) -> SessionResponse:
    return SessionResponse(
        session_id=record.session_id,
        user_id=record.user_id,
        title=record.title,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _session_summary_response(record: SessionSummaryRecord) -> SessionSummaryResponse:
    return SessionSummaryResponse(
        session_id=record.session_id,
        user_id=record.user_id,
        title=record.title,
        created_at=record.created_at,
        updated_at=record.updated_at,
        last_message=record.last_message,
    )


def _build_node_response(r: dict) -> GraphNodeResponse:
    return GraphNodeResponse(
        id=r["id"],
        label=r["label"] or r["id"][:8],
        type=r["type"],
        description=r["description"],
        aliases=r["aliases"] if isinstance(r["aliases"], list) else [],
    )


def _build_edge_response(r: dict) -> GraphEdgeResponse:
    return GraphEdgeResponse(
        id=f"{r['source']}-{r['type']}-{r['target']}",
        source=r["source"],
        target=r["target"],
        type=r["type"],
        description=r["description"],
        weight=r["weight"],
    )


@dataclass
class AppRuntime:
    chat_service: ChatService
    session_store: SqliteSessionStore
    vector_store: NanoVectorStore
    graph_store: Neo4jGraphStore


def _runtime_from_request(request: Request) -> AppRuntime:
    runtime = getattr(request.app.state, "runtime", None)
    if runtime is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="service is still starting",
        )
    return runtime


async def _get_session_or_403(
    session_store: SqliteSessionStore, session_id: str, user_id: str
) -> SessionRecord:
    session = await session_store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")
    if session.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="session access denied")
    return session


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        vector_store = NanoVectorStore()
        graph_store = Neo4jGraphStore()
        session_store = SqliteSessionStore(settings.session_db_path)

        await graph_store.initialize()
        await session_store.initialize()

        tools = [
            create_vector_search(vector_store),
            create_graph_query(graph_store),
            web_search,
        ]
        agent = build_agent_graph(tools)
        app.state.runtime = AppRuntime(
            chat_service=ChatService(
                agent=agent,
                graph_store=graph_store,
                session_store=session_store,
                history_rounds=settings.session_history_rounds,
            ),
            session_store=session_store,
            vector_store=vector_store,
            graph_store=graph_store,
        )
        logger.info(
            "FastAPI runtime ready (session_db=%s, history_rounds=%d)",
            settings.session_db_path,
            settings.session_history_rounds,
        )

        try:
            yield
        finally:
            await session_store.finalize()
            await graph_store.finalize()
            await vector_store.finalize()
            app.state.runtime = None

    app = FastAPI(
        title="KG-RAG API",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    # --- Auth endpoints (no token required) ---

    @app.post(
        "/api/v1/auth/register",
        response_model=AuthResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def register(payload: RegisterRequest, request: Request) -> AuthResponse:
        runtime = _runtime_from_request(request)
        existing = await runtime.session_store.get_user_by_username(payload.username)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="用户名已存在",
            )
        hashed = hash_password(payload.password)
        try:
            user = await runtime.session_store.create_user(payload.username, hashed)
        except sqlite3.IntegrityError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="用户名已存在",
            ) from exc
        token = create_access_token(user.user_id)
        return AuthResponse(
            user_id=user.user_id,
            username=user.username,
            access_token=token,
        )

    @app.post("/api/v1/auth/login", response_model=AuthResponse)
    async def login(payload: LoginRequest, request: Request) -> AuthResponse:
        runtime = _runtime_from_request(request)
        user = await runtime.session_store.get_user_by_username(payload.username)
        if user is None or not verify_password(payload.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户名或密码错误",
            )
        token = create_access_token(user.user_id)
        return AuthResponse(
            user_id=user.user_id,
            username=user.username,
            access_token=token,
        )

    # --- Protected session endpoints ---

    @app.post(
        "/api/v1/sessions",
        response_model=SessionResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_session(
        payload: SessionCreateRequest,
        request: Request,
        user_id: str = Depends(get_current_user_id),
    ) -> SessionResponse:
        runtime = _runtime_from_request(request)
        try:
            session = await runtime.session_store.create_session(
                user_id,
                title=payload.title,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        return _session_response(session)

    @app.get("/api/v1/sessions", response_model=list[SessionSummaryResponse])
    async def list_sessions(
        request: Request,
        user_id: str = Depends(get_current_user_id),
        limit: int = Query(default=20, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ) -> list[SessionSummaryResponse]:
        runtime = _runtime_from_request(request)
        sessions = await runtime.session_store.list_sessions(
            user_id,
            limit=limit,
            offset=offset,
        )
        return [_session_summary_response(item) for item in sessions]

    @app.get("/api/v1/sessions/{session_id}", response_model=SessionResponse)
    async def get_session(
        session_id: str,
        request: Request,
        user_id: str = Depends(get_current_user_id),
    ) -> SessionResponse:
        runtime = _runtime_from_request(request)
        session = await _get_session_or_403(runtime.session_store, session_id, user_id)
        return _session_response(session)

    @app.delete("/api/v1/sessions/{session_id}")
    async def delete_session(
        session_id: str,
        request: Request,
        user_id: str = Depends(get_current_user_id),
    ) -> dict[str, bool]:
        runtime = _runtime_from_request(request)
        deleted = await runtime.session_store.delete_session(session_id, user_id)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")
        return {"ok": True}

    @app.get(
        "/api/v1/sessions/{session_id}/messages",
        response_model=SessionMessagesResponse,
    )
    async def get_session_messages(
        session_id: str,
        request: Request,
        user_id: str = Depends(get_current_user_id),
        limit: int = Query(default=200, ge=1, le=1000),
        offset: int = Query(default=0, ge=0),
    ) -> SessionMessagesResponse:
        runtime = _runtime_from_request(request)
        session = await _get_session_or_403(runtime.session_store, session_id, user_id)

        messages = await runtime.session_store.list_messages(
            session_id,
            limit=limit,
            offset=offset,
        )
        return SessionMessagesResponse(
            session=_session_response(session),
            messages=[_message_response(item) for item in messages],
        )

    @app.post(
        "/api/v1/sessions/{session_id}/messages",
        response_model=ChatTurnResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def chat_turn(
        session_id: str,
        payload: SessionMessageCreateRequest,
        request: Request,
        user_id: str = Depends(get_current_user_id),
    ) -> ChatTurnResponse:
        runtime = _runtime_from_request(request)
        await _get_session_or_403(runtime.session_store, session_id, user_id)

        try:
            result = await runtime.chat_service.ask(
                session_id=session_id,
                user_id=user_id,
                question=payload.content,
            )
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found") from exc
        except PermissionError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("chat turn failed for session %s: %s", session_id, exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="failed to process chat turn",
            ) from exc

        return ChatTurnResponse(
            session_id=result.session.session_id,
            user_id=result.session.user_id,
            question=_message_response(result.user_message),
            answer=_message_response(result.assistant_message),
            final_answer=result.final_answer,
            iteration=result.iteration,
            history_rounds_used=result.history_rounds_used,
            todos=result.todos,
            intermediate_results=result.intermediate_results,
        )

    @app.post("/api/v1/sessions/{session_id}/chat/stream")
    async def chat_turn_stream(
        session_id: str,
        payload: SessionMessageCreateRequest,
        request: Request,
        user_id: str = Depends(get_current_user_id),
    ) -> StreamingResponse:
        runtime = _runtime_from_request(request)
        await _get_session_or_403(runtime.session_store, session_id, user_id)

        async def event_generator():
            try:
                async for event in runtime.chat_service.ask_stream(
                    session_id=session_id,
                    user_id=user_id,
                    question=payload.content,
                ):
                    event_type = event.get("event", "message")
                    data = event.get("data", {})
                    yield f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"
            except KeyError as exc:
                yield f"event: error\ndata: {json.dumps({'detail': str(exc)})}\n\n"
            except PermissionError as exc:
                yield f"event: error\ndata: {json.dumps({'detail': str(exc)})}\n\n"
            except ValueError as exc:
                yield f"event: error\ndata: {json.dumps({'detail': str(exc)})}\n\n"
            except Exception as exc:
                logger.exception("SSE stream failed for session %s: %s", session_id, exc)
                yield f"event: error\ndata: {json.dumps({'detail': 'failed to process chat turn'})}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # --- Graph visualization endpoints (read-only) ---


    @app.get("/api/v1/graph/stats", response_model=GraphStatsResponse)
    async def graph_stats(
        request: Request,
        user_id: str = Depends(get_current_user_id),
    ) -> GraphStatsResponse:
        runtime = _runtime_from_request(request)
        gs = runtime.graph_store

        entity_rows = await gs.query_cypher(
            "MATCH (e:Entity) RETURN coalesce(e.type, 'Unknown') AS t, count(e) AS c"
        )
        entities_by_type: dict[str, int] = {r["t"]: r["c"] for r in entity_rows}
        total_entities = sum(entities_by_type.values())

        rel_rows = await gs.query_cypher(
            "MATCH (:Entity)-[r]->(:Entity) RETURN type(r) AS t, count(r) AS c"
        )
        relations_by_type: dict[str, int] = {r["t"]: r["c"] for r in rel_rows}
        total_relations = sum(relations_by_type.values())

        return GraphStatsResponse(
            total_entities=total_entities,
            total_relations=total_relations,
            entities_by_type=entities_by_type,
            relations_by_type=relations_by_type,
        )

    @app.get("/api/v1/graph/overview", response_model=GraphOverviewResponse)
    async def graph_overview(
        request: Request,
        user_id: str = Depends(get_current_user_id),
        entity_type: str | None = Query(default=None),
        limit: int = Query(default=500, ge=1, le=2000),
    ) -> GraphOverviewResponse:
        runtime = _runtime_from_request(request)
        gs = runtime.graph_store

        if entity_type and entity_type not in ENTITY_TYPE_LABELS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid entity_type. Must be one of: {sorted(ENTITY_TYPE_LABELS)}",
            )

        if entity_type:
            node_cypher = (
                f"MATCH (e:{entity_type}) "
                "OPTIONAL MATCH (e)-[r]-() "
                "WITH e, count(r) AS degree "
                "ORDER BY degree DESC "
                "LIMIT $limit "
                "RETURN e.entity_id AS id, e.name AS label, "
                "coalesce(e.type, 'Unknown') AS type, "
                "coalesce(e.description, '') AS description, "
                "coalesce(e.aliases, []) AS aliases"
            )
        else:
            node_cypher = (
                "MATCH (e:Entity) "
                "OPTIONAL MATCH (e)-[r]-() "
                "WITH e, count(r) AS degree "
                "ORDER BY degree DESC "
                "LIMIT $limit "
                "RETURN e.entity_id AS id, e.name AS label, "
                "coalesce(e.type, 'Unknown') AS type, "
                "coalesce(e.description, '') AS description, "
                "coalesce(e.aliases, []) AS aliases"
            )

        node_rows = await gs.query_cypher(node_cypher, {"limit": limit})
        node_ids = {r["id"] for r in node_rows}
        is_truncated = len(node_rows) >= limit

        nodes = [_build_node_response(r) for r in node_rows]

        if node_ids:
            edge_rows = await gs.query_cypher(
                "MATCH (a:Entity)-[r]->(b:Entity) "
                "WHERE a.entity_id IN $ids AND b.entity_id IN $ids "
                "RETURN a.entity_id AS source, b.entity_id AS target, "
                "type(r) AS type, coalesce(r.description, '') AS description, "
                "coalesce(r.weight, 1.0) AS weight",
                {"ids": list(node_ids)},
            )
            edges = [_build_edge_response(r) for r in edge_rows]
        else:
            edges = []

        return GraphOverviewResponse(nodes=nodes, edges=edges, is_truncated=is_truncated)

    @app.get("/api/v1/graph/entities/search")
    async def graph_entity_search(
        request: Request,
        user_id: str = Depends(get_current_user_id),
        q: str = Query(min_length=1),
        entity_type: str | None = Query(default=None),
        limit: int = Query(default=20, ge=1, le=100),
    ) -> list[GraphNodeResponse]:
        runtime = _runtime_from_request(request)
        gs = runtime.graph_store

        if entity_type and entity_type not in ENTITY_TYPE_LABELS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid entity_type. Must be one of: {sorted(ENTITY_TYPE_LABELS)}",
            )

        type_filter = f":{entity_type}" if entity_type else ":Entity"
        cypher = (
            f"MATCH (e{type_filter}) "
            "WHERE toLower(e.name) CONTAINS toLower($q) "
            "   OR ANY(a IN coalesce(e.aliases, []) WHERE toLower(a) CONTAINS toLower($q)) "
            "RETURN e.entity_id AS id, e.name AS label, "
            "coalesce(e.type, 'Unknown') AS type, "
            "coalesce(e.description, '') AS description, "
            "coalesce(e.aliases, []) AS aliases "
            "LIMIT $limit"
        )
        rows = await gs.query_cypher(cypher, {"q": q, "limit": limit})
        return [_build_node_response(r) for r in rows]

    @app.get("/api/v1/graph/entities/{entity_id}/neighbors", response_model=GraphOverviewResponse)
    async def graph_entity_neighbors(
        entity_id: str,
        request: Request,
        user_id: str = Depends(get_current_user_id),
        depth: int = Query(default=1, ge=1, le=3),
        limit: int = Query(default=50, ge=1, le=200),
    ) -> GraphOverviewResponse:
        runtime = _runtime_from_request(request)
        gs = runtime.graph_store

        center = await gs.query_cypher(
            "MATCH (e:Entity {entity_id: $eid}) "
            "RETURN e.entity_id AS id, e.name AS label, "
            "coalesce(e.type, 'Unknown') AS type, "
            "coalesce(e.description, '') AS description, "
            "coalesce(e.aliases, []) AS aliases",
            {"eid": entity_id},
        )
        if not center:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="entity not found")

        neighbor_rows = await gs.query_cypher(
            f"MATCH (center:Entity {{entity_id: $eid}})-[*1..{depth}]-(neighbor:Entity) "
            "RETURN DISTINCT neighbor.entity_id AS id, neighbor.name AS label, "
            "coalesce(neighbor.type, 'Unknown') AS type, "
            "coalesce(neighbor.description, '') AS description, "
            "coalesce(neighbor.aliases, []) AS aliases "
            "LIMIT $limit",
            {"eid": entity_id, "limit": limit},
        )

        all_rows = center + neighbor_rows
        node_ids = {r["id"] for r in all_rows}
        nodes = [_build_node_response(r) for r in all_rows]

        edge_rows = await gs.query_cypher(
            "MATCH (a:Entity)-[r]->(b:Entity) "
            "WHERE a.entity_id IN $ids AND b.entity_id IN $ids "
            "RETURN a.entity_id AS source, b.entity_id AS target, "
            "type(r) AS type, coalesce(r.description, '') AS description, "
            "coalesce(r.weight, 1.0) AS weight",
            {"ids": list(node_ids)},
        )
        edges = [_build_edge_response(r) for r in edge_rows]

        return GraphOverviewResponse(
            nodes=nodes,
            edges=edges,
            is_truncated=len(neighbor_rows) >= limit,
        )

    return app
