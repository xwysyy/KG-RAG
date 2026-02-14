"""Application service layer for session-based chat."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol

from langchain_core.messages import AIMessage, HumanMessage

from kg_rag.api.session_store import (
    MessageRecord,
    SessionRecord,
    SqliteSessionStore,
)
from kg_rag.config import settings
from kg_rag.memory.profile import read_profile
from kg_rag.memory.proposal import (
    apply_proposals,
    extract_proposals,
    filter_proposals,
)

logger = logging.getLogger(__name__)


class _AgentRunner(Protocol):
    async def ainvoke(self, state: dict[str, Any]) -> dict[str, Any]: ...

    def astream(
        self,
        state: dict[str, Any],
        *,
        stream_mode: list[str] | None = None,
        config: dict[str, Any] | None = None,
    ) -> Any: ...


ProfileReader = Callable[[str, Any], Awaitable[str]]
ProposalExtractor = Callable[[str, str], Awaitable[list[Any]]]
ProposalFilter = Callable[[list[Any]], list[Any]]
ProposalApplier = Callable[[list[Any], Any], Awaitable[int]]


@dataclass(frozen=True)
class TurnResult:
    session: SessionRecord
    user_message: MessageRecord
    assistant_message: MessageRecord
    final_answer: str
    iteration: int
    todos: list[dict[str, Any]]
    intermediate_results: list[str]
    history_rounds_used: int


class ChatService:
    """Coordinates persistence, user profile, and LangGraph invocation."""

    def __init__(
        self,
        *,
        agent: _AgentRunner,
        graph_store: Any,
        session_store: SqliteSessionStore,
        history_rounds: int | None = None,
        profile_reader: ProfileReader = read_profile,
        proposal_extractor: ProposalExtractor = extract_proposals,
        proposal_filter: ProposalFilter = filter_proposals,
        proposal_applier: ProposalApplier = apply_proposals,
    ) -> None:
        self._agent = agent
        self._graph_store = graph_store
        self._session_store = session_store
        self._history_rounds = (
            history_rounds
            if history_rounds is not None
            else settings.session_history_rounds
        )
        self._profile_reader = profile_reader
        self._proposal_extractor = proposal_extractor
        self._proposal_filter = proposal_filter
        self._proposal_applier = proposal_applier

    async def ask(self, session_id: str, user_id: str, question: str) -> TurnResult:
        clean_question = question.strip()
        if not clean_question:
            raise ValueError("question cannot be empty")

        session = await self._session_store.get_session(session_id)
        if session is None:
            raise KeyError(f"session {session_id} not found")
        if session.user_id != user_id:
            raise PermissionError("session does not belong to current user")

        history_rounds = await self._session_store.get_recent_rounds(
            session_id,
            max_rounds=self._history_rounds,
        )

        user_message = await self._session_store.append_message(
            session_id,
            role="user",
            content=clean_question,
        )

        history_messages = []
        for user_text, assistant_text in history_rounds:
            history_messages.append(HumanMessage(content=user_text))
            history_messages.append(AIMessage(content=assistant_text))
        history_messages.append(HumanMessage(content=clean_question))

        profile = await self._profile_reader(user_id, self._graph_store)
        result = await self._agent.ainvoke(
            {
                "messages": history_messages,
                "todos": [],
                "user_profile": profile,
                "iteration": 0,
                "max_iterations": settings.max_iterations,
                "intermediate_results": [],
                "final_answer": "",
            }
        )

        answer = str(result.get("final_answer", "")).strip()
        if not answer:
            answer = "抱歉，我暂时无法生成可用回答。"

        assistant_message = await self._session_store.append_message(
            session_id,
            role="assistant",
            content=answer,
        )

        await self._update_profile_from_turn(
            user_id=user_id,
            question=clean_question,
            answer=answer,
        )

        latest_session = await self._session_store.get_session(session_id)
        if latest_session is None:
            raise RuntimeError("session disappeared after successful write")

        todos = result.get("todos") or []
        if not isinstance(todos, list):
            todos = []

        intermediate = result.get("intermediate_results") or []
        if not isinstance(intermediate, list):
            intermediate = []

        iteration_raw = result.get("iteration", 0)
        try:
            iteration = int(iteration_raw)
        except (TypeError, ValueError):
            iteration = 0

        return TurnResult(
            session=latest_session,
            user_message=user_message,
            assistant_message=assistant_message,
            final_answer=answer,
            iteration=iteration,
            todos=todos,
            intermediate_results=[str(item) for item in intermediate],
            history_rounds_used=len(history_rounds),
        )

    async def ask_stream(
        self, session_id: str, user_id: str, question: str
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Streaming variant of ``ask()`` — yields SSE-ready event dicts."""
        clean_question = question.strip()
        if not clean_question:
            raise ValueError("question cannot be empty")

        session = await self._session_store.get_session(session_id)
        if session is None:
            raise KeyError(f"session {session_id} not found")
        if session.user_id != user_id:
            raise PermissionError("session does not belong to current user")

        history_rounds = await self._session_store.get_recent_rounds(
            session_id,
            max_rounds=self._history_rounds,
        )

        user_message = await self._session_store.append_message(
            session_id,
            role="user",
            content=clean_question,
        )

        # Yield metadata event
        yield {
            "event": "metadata",
            "data": {
                "session_id": session_id,
                "user_message": {
                    "message_id": user_message.message_id,
                    "session_id": user_message.session_id,
                    "role": user_message.role,
                    "content": user_message.content,
                    "created_at": user_message.created_at,
                },
            },
        }

        history_messages = []
        for user_text, assistant_text in history_rounds:
            history_messages.append(HumanMessage(content=user_text))
            history_messages.append(AIMessage(content=assistant_text))
        history_messages.append(HumanMessage(content=clean_question))

        profile = await self._profile_reader(user_id, self._graph_store)
        state = {
            "messages": history_messages,
            "todos": [],
            "user_profile": profile,
            "iteration": 0,
            "max_iterations": settings.max_iterations,
            "intermediate_results": [],
            "final_answer": "",
        }

        # Stream execution
        final_state = None
        async for mode, chunk in self._agent.astream(
            state,
            stream_mode=["values", "custom"],
            config={"recursion_limit": 100},
        ):
            if mode == "custom":
                yield {"event": "custom", "data": chunk}
            elif mode == "values":
                final_state = chunk
                yield {
                    "event": "state",
                    "data": {
                        "phase": _compute_phase(chunk),
                        "todos": _serialize_todos(chunk),
                        "final_answer": str(chunk.get("final_answer", "")),
                        "iteration": _safe_int(chunk.get("iteration", 0)),
                    },
                }

        # Persist assistant message
        if final_state is None:
            final_state = state

        answer = str(final_state.get("final_answer", "")).strip()
        if not answer or answer == "__READY__":
            answer = "抱歉，我暂时无法生成可用回答。"

        assistant_message = await self._session_store.append_message(
            session_id,
            role="assistant",
            content=answer,
        )

        # Yield done event immediately (profile update runs after)
        yield {
            "event": "done",
            "data": {
                "assistant_message": {
                    "message_id": assistant_message.message_id,
                    "session_id": assistant_message.session_id,
                    "role": assistant_message.role,
                    "content": assistant_message.content,
                    "created_at": assistant_message.created_at,
                },
                "final_answer": answer,
            },
        }

        await self._update_profile_from_turn(
            user_id=user_id,
            question=clean_question,
            answer=answer,
        )

    async def _update_profile_from_turn(
        self,
        *,
        user_id: str,
        question: str,
        answer: str,
    ) -> None:
        try:
            conversation = f"User: {question}\nAssistant: {answer}"
            proposals = await self._proposal_extractor(conversation, user_id)
            accepted = self._proposal_filter(proposals)
            if accepted:
                await self._proposal_applier(accepted, self._graph_store)
        except Exception as exc:
            logger.warning("Profile extraction/update failed for user %s: %s", user_id, exc)


def _safe_int(value: Any) -> int:
    """Safely convert value to int, returning 0 on failure."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _compute_phase(state: dict[str, Any]) -> str:
    """Compute agent phase from state, mirroring frontend useAgentPhase logic."""
    final_answer = str(state.get("final_answer", ""))
    if final_answer == "__READY__":
        return "answering"

    todos = state.get("todos") or []
    if isinstance(todos, list) and any(
        isinstance(t, dict) and t.get("status") == "in_progress" for t in todos
    ):
        return "executing"

    # Check last AI message for aggregated/review markers
    messages = state.get("messages") or []
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            content = msg.content if isinstance(msg.content, str) else ""
            if content.startswith("[Aggregated Results]") or content.startswith(
                "[Quality Review]"
            ):
                return "reviewing"
            break

    return "planning"


def _serialize_todos(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Safely serialize todos from agent state."""
    _VALID_STATUSES = {"pending", "in_progress", "completed"}
    todos = state.get("todos") or []
    if not isinstance(todos, list):
        return []
    result = []
    for t in todos:
        if not isinstance(t, dict):
            continue
        tid = str(t.get("id", "")).strip()
        if not tid:
            continue
        raw_status = str(t.get("status", "pending"))
        status = raw_status if raw_status in _VALID_STATUSES else "pending"
        result.append(
            {
                "id": tid,
                "content": str(t.get("content", "")),
                "status": status,
            }
        )
    return result
