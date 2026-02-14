"""LangGraph agent state definition."""

from __future__ import annotations

from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """Top-level state flowing through the agent graph.

    ``messages`` uses the LangGraph ``add_messages`` reducer so that
    every node can simply *append* new messages rather than replacing
    the full list.
    """

    messages: Annotated[list[BaseMessage], add_messages]

    # Plan Agent produces a list of sub-task dicts:
    #   [{"id": "1", "content": "...", "status": "pending"}, ...]
    # UI (deep-agents-ui) reads `content` for display and `status` for grouping.
    todos: list[dict]

    # Serialised user profile string injected into the system prompt
    user_profile: str

    # Current iteration counter and ceiling
    iteration: int
    max_iterations: int

    # Aggregated intermediate results from sub-agents
    intermediate_results: list[str]

    # Final answer (set by the respond node)
    final_answer: str

    # Files produced during execution (reserved for UI, default empty)
    files: dict[str, str]
