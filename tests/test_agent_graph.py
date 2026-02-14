"""Tests for kg_rag.agent.graph (pure helper logic + node integration)."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from kg_rag.agent import graph as agent_graph


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_state(**overrides) -> dict:
    base = {
        "messages": [HumanMessage(content="What is BFS?")],
        "todos": [],
        "user_profile": "",
        "iteration": 0,
        "max_iterations": 3,
        "intermediate_results": [],
        "final_answer": "",
        "files": {},
    }
    base.update(overrides)
    return base


def _dummy_llm(content: str) -> AsyncMock:
    llm = AsyncMock()
    llm.ainvoke.return_value = SimpleNamespace(content=content)
    async def _stream():
        yield SimpleNamespace(content=content, additional_kwargs={})
    # LangChain's `astream()` returns an async iterator (not a coroutine).
    llm.astream = Mock(return_value=_stream())
    return llm


# ---------------------------------------------------------------------------
# Existing pure-logic tests
# ---------------------------------------------------------------------------

class TestParseTodos:
    def test_parses_json_from_code_fence(self):
        text = (
            "```json\n"
            '[{"id": 1, "task": "t1", "tool_hint": "vector_search"}]\n'
            "```"
        )
        todos = agent_graph._parse_todos(text)
        assert todos == [{"id": "1", "content": "t1", "status": "pending"}]

    def test_fallbacks_when_no_json(self):
        text = "not json at all"
        todos = agent_graph._parse_todos(text)
        assert todos == [{"id": "1", "content": text, "status": "pending"}]

    def test_validates_items(self):
        text = '["raw item", {"task": "t2", "tool_hint": "graph_query"}]'
        todos = agent_graph._parse_todos(text)
        assert todos[0]["id"] == "1"
        assert todos[0]["content"] == "raw item"
        assert todos[0]["status"] == "pending"
        assert todos[1]["content"] == "t2"
        assert todos[1]["status"] == "pending"

    def test_empty_list_falls_back(self):
        text = "[]"
        todos = agent_graph._parse_todos(text)
        assert len(todos) == 1
        assert todos[0]["id"] == "1"
        assert todos[0]["content"] == text


class TestShouldContinue:
    def test_routes_based_on_final_answer_presence(self):
        assert agent_graph._should_continue({"final_answer": "x"}) == "respond"
        assert agent_graph._should_continue({"final_answer": ""}) == "plan"
        assert agent_graph._should_continue({}) == "plan"


class TestDialogueHistory:
    def test_extracts_only_user_and_final_answer_last_five_rounds(self):
        messages = []
        for idx in range(1, 8):
            messages.append(HumanMessage(content=f"q{idx}"))
            messages.append(AIMessage(content=f"[Plan] p{idx}"))
            messages.append(AIMessage(content=f"a{idx}"))

        rounds = agent_graph._extract_recent_dialogue_rounds(messages, max_rounds=5)

        assert len(rounds) == 5
        assert rounds[0] == ("q3", "a3")
        assert rounds[-1] == ("q7", "a7")

    def test_skips_tool_call_and_think_content(self):
        messages = [
            HumanMessage(content="Explain heap"),
            AIMessage(content="Thought only", tool_calls=[{"id": "t1", "name": "vector_search", "args": {}}]),
            AIMessage(content="<think>internal</think>Heap is a complete binary tree."),
        ]
        rounds = agent_graph._extract_recent_dialogue_rounds(messages)
        assert rounds == [("Explain heap", "Heap is a complete binary tree.")]


# ---------------------------------------------------------------------------
# Node integration tests
# ---------------------------------------------------------------------------

class TestPlanNode:
    @pytest.mark.asyncio
    async def test_produces_todos(self):
        todos_json = json.dumps([
            {"id": 1, "task": "Search BFS", "tool_hint": "vector_search"},
        ])
        with patch(
            "kg_rag.agent.graph._stream_reasoning_chat",
            new=AsyncMock(return_value=(todos_json, "planning reasoning")),
        ):
            result = await agent_graph.plan_node(_make_state())
        assert len(result["todos"]) == 1
        assert result["todos"][0]["content"] == "Search BFS"
        assert result["todos"][0]["status"] == "pending"
        assert result["iteration"] == 1

    @pytest.mark.asyncio
    async def test_replan_includes_previous_results(self):
        captured_messages = {}

        async def _fake_stream(messages, **kwargs):
            captured_messages["messages"] = messages
            return '[{"id":1,"task":"refine","tool_hint":"graph_query"}]', ""

        state = _make_state(
            iteration=1,
            intermediate_results=["Previous result about BFS"],
        )
        with patch(
            "kg_rag.agent.graph._stream_reasoning_chat",
            new=AsyncMock(side_effect=_fake_stream),
        ):
            await agent_graph.plan_node(state)
        # Verify the LLM was called with a prompt mentioning re-plan
        call_args = captured_messages.get("messages", [])
        messages_text = " ".join(msg.get("content", "") for msg in call_args)
        assert "Re-plan" in messages_text

    @pytest.mark.asyncio
    async def test_uses_recent_dialogue_context_up_to_five_rounds(self):
        captured_messages = {}

        async def _fake_stream(messages, **kwargs):
            captured_messages["messages"] = messages
            return '[{"id":1,"task":"refine","tool_hint":"graph_query"}]', ""

        history_messages = []
        for idx in range(1, 7):
            history_messages.append(HumanMessage(content=f"history-q{idx}"))
            history_messages.append(AIMessage(content=f"history-a{idx}"))
        # Current turn (no final answer yet)
        history_messages.append(HumanMessage(content="current question"))
        history_messages.append(AIMessage(content="[Plan] should be ignored"))

        state = _make_state(messages=history_messages)
        with patch(
            "kg_rag.agent.graph._stream_reasoning_chat",
            new=AsyncMock(side_effect=_fake_stream),
        ):
            await agent_graph.plan_node(state)

        messages_text = " ".join(
            msg.get("content", "") for msg in captured_messages.get("messages", [])
        )
        assert "Previous conversation context" in messages_text
        assert "history-q1" not in messages_text  # capped to latest 5 rounds
        assert "history-q2" in messages_text
        assert "history-a6" in messages_text
        assert "current question" in messages_text
        assert "[Plan] should be ignored" not in messages_text


class TestExecuteNode:
    @pytest.mark.asyncio
    async def test_spawns_sub_agents(self):
        state = _make_state(
            todos=[{"id": "1", "content": "Search BFS", "status": "pending"}],
        )
        llm = _dummy_llm("")
        with (
            patch("kg_rag.agent.graph._build_llm", return_value=llm),
            patch(
                "kg_rag.agent.graph._run_react_loop",
                new_callable=AsyncMock,
                return_value=("BFS is a graph traversal algorithm.", []),
            ),
        ):
            result = await agent_graph.execute_node(state, tools=[])
        assert len(result["intermediate_results"]) == 1
        assert "BFS" in result["intermediate_results"][0]
        assert result["todos"][0]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_empty_todos(self):
        state = _make_state(todos=[])
        result = await agent_graph.execute_node(state, tools=[])
        assert "No sub-tasks" in result["intermediate_results"][0]

    @pytest.mark.asyncio
    async def test_sub_agent_exception_isolated(self):
        """单个子任务异常不影响其他子任务结果收集。"""
        state = _make_state(todos=[
            {"id": "1", "content": "fail task", "status": "pending"},
            {"id": "2", "content": "ok task", "status": "pending"},
        ])

        call_count = 0

        async def _fake_loop(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("boom")
            return ("OK result", [])

        llm = _dummy_llm("")
        with (
            patch("kg_rag.agent.graph._build_llm", return_value=llm),
            patch("kg_rag.agent.graph._run_react_loop", side_effect=_fake_loop),
        ):
            result = await agent_graph.execute_node(state, tools=[])
        assert len(result["intermediate_results"]) == 2
        assert "ERROR" in result["intermediate_results"][0]
        assert "OK result" in result["intermediate_results"][1]


class TestAggregateNode:
    @pytest.mark.asyncio
    async def test_merges_results(self):
        state = _make_state(
            intermediate_results=["Result A", "Result B"],
        )
        result = await agent_graph.aggregate_node(state)
        msgs = result["messages"]
        assert len(msgs) == 1
        assert "Result A" in msgs[0].content
        assert "Result B" in msgs[0].content

    @pytest.mark.asyncio
    async def test_empty_results(self):
        state = _make_state(intermediate_results=[])
        result = await agent_graph.aggregate_node(state)
        assert "No results collected" in result["messages"][0].content


class TestJudgeNode:
    @pytest.mark.asyncio
    async def test_sufficient_verdict(self):
        llm = _dummy_llm("SUFFICIENT")
        state = _make_state(
            iteration=1,
            intermediate_results=["BFS uses a queue for level-order traversal."],
        )
        with patch("kg_rag.agent.graph._build_reasoning_llm", return_value=llm):
            result = await agent_graph.judge_node(state)
        assert result["final_answer"] == "__READY__"
        assert result["messages"][0].content.startswith("[Quality Review]")

    @pytest.mark.asyncio
    async def test_insufficient_verdict(self):
        llm = _dummy_llm("INSUFFICIENT — missing complexity analysis")
        state = _make_state(
            iteration=1,
            intermediate_results=["partial info"],
        )
        with patch("kg_rag.agent.graph._build_reasoning_llm", return_value=llm):
            result = await agent_graph.judge_node(state)
        assert result["final_answer"] == ""
        assert result["messages"][0].content.startswith("[Quality Review]")

    @pytest.mark.asyncio
    async def test_uses_last_human_message(self):
        """judge_node should use the LAST HumanMessage, not the first."""
        llm = _dummy_llm("SUFFICIENT")
        state = _make_state(
            messages=[
                HumanMessage(content="What is BFS?"),
                AIMessage(content="[Plan] ..."),
                HumanMessage(content="What is DFS?"),
            ],
            iteration=1,
            intermediate_results=["DFS info"],
        )
        with patch("kg_rag.agent.graph._build_reasoning_llm", return_value=llm):
            await agent_graph.judge_node(state)
        if llm.astream.call_args:
            call_args = llm.astream.call_args.args[0]
        else:
            call_args = llm.ainvoke.call_args.args[0]
        prompt_text = call_args[0].content if hasattr(call_args[0], "content") else str(call_args)
        assert "DFS" in prompt_text

    @pytest.mark.asyncio
    async def test_max_iterations_forces_ready(self):
        llm = _dummy_llm("INSUFFICIENT — still missing info")
        state = _make_state(
            iteration=3,
            max_iterations=3,
            intermediate_results=["partial"],
        )
        with patch("kg_rag.agent.graph._build_reasoning_llm", return_value=llm):
            result = await agent_graph.judge_node(state)
        assert result["final_answer"] == "__READY__"
        assert result["messages"][0].content.startswith("[Quality Review]")


class TestRespondNode:
    @pytest.mark.asyncio
    async def test_generates_final_answer(self):
        state = _make_state(
            intermediate_results=["BFS uses queue, O(V+E) complexity"],
        )
        with patch(
            "kg_rag.agent.graph._stream_reasoning_completion",
            new=AsyncMock(return_value=("BFS is a graph traversal algorithm using a queue.", "")),
        ):
            result = await agent_graph.respond_node(state)
        assert result["final_answer"]
        assert "BFS" in result["final_answer"]

    @pytest.mark.asyncio
    async def test_uses_last_human_message(self):
        """respond_node should use the LAST HumanMessage, not the first."""
        state = _make_state(
            messages=[
                HumanMessage(content="What is BFS?"),
                AIMessage(content="[Plan] ..."),
                HumanMessage(content="What is DFS?"),
            ],
            intermediate_results=["DFS info"],
        )

        captured_prompt = {}

        async def _fake_stream(prompt: str, **kwargs):
            captured_prompt["prompt"] = prompt
            return "DFS answer", ""

        with patch(
            "kg_rag.agent.graph._stream_reasoning_completion",
            new=AsyncMock(side_effect=_fake_stream),
        ):
            await agent_graph.respond_node(state)

        prompt_text = captured_prompt.get("prompt", "")
        assert "DFS" in prompt_text


# ---------------------------------------------------------------------------
# _run_react_loop integration tests
# ---------------------------------------------------------------------------

class TestRunReactLoop:
    """Tests for the text-based ReAct loop."""

    @pytest.mark.asyncio
    async def test_single_tool_then_final_answer(self):
        """Tool call → Observation → Final Answer."""
        llm = AsyncMock()
        llm.ainvoke = AsyncMock(side_effect=[
            SimpleNamespace(content=(
                "Thought: I need to search for BFS.\n"
                "Action: vector_search\n"
                "Action Input: BFS algorithm"
            )),
            SimpleNamespace(content=(
                "Thought: I have the info.\n"
                "Final Answer: BFS is a graph traversal algorithm."
            )),
        ])

        mock_tool = AsyncMock(spec=["name", "ainvoke"])
        mock_tool.name = "vector_search"
        mock_tool.ainvoke = AsyncMock(return_value="BFS uses a queue for level-order traversal.")

        answer, state_msgs = await agent_graph._run_react_loop(
            llm=llm, system_prompt="sys", task="What is BFS?", tools=[mock_tool],
        )
        assert "BFS is a graph traversal algorithm" in answer
        mock_tool.ainvoke.assert_called_once_with("BFS algorithm")
        # Should have 1 AIMessage with tool_calls + 1 ToolMessage
        assert len(state_msgs) == 2
        assert hasattr(state_msgs[0], "tool_calls")
        assert state_msgs[0].tool_calls[0]["name"] == "vector_search"

    @pytest.mark.asyncio
    async def test_direct_final_answer(self):
        """LLM gives Final Answer on first turn — no tool calls."""
        llm = _dummy_llm("Thought: I already know.\nFinal Answer: BFS uses a queue.")
        answer, state_msgs = await agent_graph._run_react_loop(
            llm=llm, system_prompt="sys", task="What is BFS?", tools=[],
        )
        assert "BFS uses a queue" in answer
        assert len(state_msgs) == 0

    @pytest.mark.asyncio
    async def test_unknown_tool_self_correction(self):
        """Unknown tool name → error observation → LLM self-corrects."""
        llm = AsyncMock()
        llm.ainvoke = AsyncMock(side_effect=[
            SimpleNamespace(content=(
                "Thought: search\n"
                "Action: bad_tool\n"
                "Action Input: query"
            )),
            SimpleNamespace(content=(
                "Thought: let me use the right tool\n"
                "Action: vector_search\n"
                "Action Input: BFS"
            )),
            SimpleNamespace(content=(
                "Thought: got it\n"
                "Final Answer: BFS answer"
            )),
        ])

        mock_tool = AsyncMock(spec=["name", "ainvoke"])
        mock_tool.name = "vector_search"
        mock_tool.ainvoke = AsyncMock(return_value="BFS info")

        answer, state_msgs = await agent_graph._run_react_loop(
            llm=llm, system_prompt="sys", task="BFS?", tools=[mock_tool],
        )
        assert "BFS answer" in answer
        # 2 tool calls (bad_tool + vector_search) → 4 state messages
        assert len(state_msgs) == 4

    @pytest.mark.asyncio
    async def test_malformed_output_graceful_degradation(self):
        """Unparseable output → one-shot format repair → still unparseable → return raw text."""
        llm = _dummy_llm("I don't know how to format this properly.")
        answer, state_msgs = await agent_graph._run_react_loop(
            llm=llm, system_prompt="sys", task="task", tools=[],
        )
        assert "I don't know how to format this properly." in answer
        assert len(state_msgs) == 0
        assert llm.ainvoke.call_count == 2  # initial + repair

    @pytest.mark.asyncio
    async def test_max_steps_forces_final_answer(self):
        """Exceeding max_steps triggers forced final answer."""
        action_response = SimpleNamespace(content=(
            "Thought: searching\n"
            "Action: vector_search\n"
            "Action Input: query"
        ))
        forced_response = SimpleNamespace(content=(
            "Final Answer: forced summary"
        ))

        call_count = 0

        async def _side_effect(messages):
            nonlocal call_count
            call_count += 1
            # max_steps=2 → 2 action calls + 1 forced call
            if call_count <= 2:
                return action_response
            return forced_response

        llm = AsyncMock()
        llm.ainvoke = AsyncMock(side_effect=_side_effect)

        mock_tool = AsyncMock(spec=["name", "ainvoke"])
        mock_tool.name = "vector_search"
        mock_tool.ainvoke = AsyncMock(return_value="some result")

        answer, state_msgs = await agent_graph._run_react_loop(
            llm=llm, system_prompt="sys", task="task",
            tools=[mock_tool], max_steps=2,
        )
        assert "forced summary" in answer
        assert call_count == 3  # 2 action steps + 1 forced
        # 2 tool calls → 4 state messages
        assert len(state_msgs) == 4
