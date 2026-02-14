"""Pydantic request/response schemas for API endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


# --- Auth schemas ---

class RegisterRequest(BaseModel):
    username: str = Field(min_length=2, max_length=32)
    password: str = Field(min_length=6, max_length=128)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class AuthResponse(BaseModel):
    user_id: str
    username: str
    access_token: str
    token_type: str = "bearer"


# --- Session schemas ---

class SessionCreateRequest(BaseModel):
    title: str = Field(default="", max_length=200)


class SessionResponse(BaseModel):
    session_id: str
    user_id: str
    title: str
    created_at: str
    updated_at: str


class SessionSummaryResponse(SessionResponse):
    last_message: str | None = None


class MessageResponse(BaseModel):
    message_id: int
    session_id: str
    role: str
    content: str
    created_at: str


class SessionMessagesResponse(BaseModel):
    session: SessionResponse
    messages: list[MessageResponse]


class SessionMessageCreateRequest(BaseModel):
    content: str = Field(min_length=1)


class ChatTurnResponse(BaseModel):
    session_id: str
    user_id: str
    question: MessageResponse
    answer: MessageResponse
    final_answer: str
    iteration: int
    history_rounds_used: int
    todos: list[dict] = Field(default_factory=list)
    intermediate_results: list[str] = Field(default_factory=list)


# --- Graph schemas ---

class GraphNodeResponse(BaseModel):
    id: str
    label: str
    type: str
    description: str = ""
    aliases: list[str] = Field(default_factory=list)


class GraphEdgeResponse(BaseModel):
    id: str
    source: str
    target: str
    type: str
    description: str = ""
    weight: float = 1.0


class GraphOverviewResponse(BaseModel):
    nodes: list[GraphNodeResponse]
    edges: list[GraphEdgeResponse]
    is_truncated: bool = False


class GraphStatsResponse(BaseModel):
    total_entities: int
    total_relations: int
    entities_by_type: dict[str, int]
    relations_by_type: dict[str, int]
