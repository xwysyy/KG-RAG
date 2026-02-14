"""Tests for kg_rag.utils."""

from kg_rag.utils import (
    ReActAction,
    parse_final_answer,
    parse_react_action,
    strip_code_fences,
)


class TestStripCodeFences:
    def test_removes_opening_and_closing_fences(self):
        text = '```json\n{"key": "value"}\n```'
        result = strip_code_fences(text)
        assert '{"key": "value"}' in result
        assert "```" not in result

    def test_no_fences_returns_unchanged(self):
        text = "plain text\nno fences here"
        assert strip_code_fences(text) == text

    def test_preserves_non_fence_lines(self):
        text = "```cypher\nMATCH (n) RETURN n\n```"
        result = strip_code_fences(text)
        assert "MATCH (n) RETURN n" in result
        assert "```" not in result

    def test_empty_string(self):
        assert strip_code_fences("") == ""

    def test_fence_with_language_tag(self):
        text = "```python\nprint('hello')\n```"
        result = strip_code_fences(text)
        assert "print('hello')" in result
        assert "```" not in result

    def test_indented_fences(self):
        text = "  ```\ncode\n  ```"
        result = strip_code_fences(text)
        assert "```" not in result
        assert "code" in result


class TestParseReactAction:
    def test_standard_format(self):
        text = "Thought: I need to search\nAction: vector_search\nAction Input: BFS algorithm"
        result = parse_react_action(text)
        assert result == ReActAction(tool="vector_search", tool_input="BFS algorithm")

    def test_extra_whitespace(self):
        text = "Thought: thinking\nAction :  graph_query \nAction  Input :  MATCH (n) RETURN n"
        result = parse_react_action(text)
        assert result is not None
        assert result.tool == "graph_query"
        assert result.tool_input == "MATCH (n) RETURN n"

    def test_final_answer_no_match(self):
        text = "Thought: done\nFinal Answer: BFS uses a queue"
        result = parse_react_action(text)
        assert result is None

    def test_empty_string(self):
        assert parse_react_action("") is None

    def test_no_action_input(self):
        text = "Action: vector_search"
        assert parse_react_action(text) is None

    def test_multiline_action_input_captures_first_line_only(self):
        """Action Input with trailing lines — only the first line is captured."""
        text = (
            "Action: vector_search\n"
            "Action Input: BFS algorithm\n"
            "Final Answer: should not be part of input"
        )
        result = parse_react_action(text)
        assert result is not None
        assert result.tool_input == "BFS algorithm"
        assert "Final Answer" not in result.tool_input

    def test_mid_line_action_not_matched(self):
        """'Action:' appearing mid-line (not at line start) should not match."""
        text = "I think the Action: vector_search\nAction Input: query"
        assert parse_react_action(text) is None

    def test_example_block_before_real_action(self):
        """When an example Action block precedes the real one, the last match wins by default."""
        text = (
            "Thought: The format is:\n"
            "Action: example_tool\n"
            "Action Input: example query\n"
            "\n"
            "Now for real:\n"
            "Action: vector_search\n"
            "Action Input: BFS"
        )
        result = parse_react_action(text)
        assert result is not None
        assert result.tool == "vector_search"

    def test_allowed_tools_prefers_allowed_tool_over_last_match(self):
        text = (
            "Action: vector_search\n"
            "Action Input: BFS\n"
            "Action: unknown_tool\n"
            "Action Input: ignore"
        )
        result = parse_react_action(text, allowed_tools={"vector_search"})
        assert result is not None
        assert result.tool == "vector_search"


class TestParseFinalAnswer:
    def test_standard_format(self):
        text = "Thought: summarizing\nFinal Answer: BFS is a graph traversal algorithm."
        result = parse_final_answer(text)
        assert result == "BFS is a graph traversal algorithm."

    def test_multiline_content(self):
        text = "Final Answer: Line one.\nLine two.\nLine three."
        result = parse_final_answer(text)
        assert "Line one." in result
        assert "Line three." in result

    def test_no_match(self):
        text = "Thought: I need to search\nAction: vector_search\nAction Input: BFS"
        assert parse_final_answer(text) is None

    def test_empty_string(self):
        assert parse_final_answer("") is None

    def test_mid_line_final_answer_not_matched(self):
        """'Final Answer:' appearing mid-line should not match."""
        text = "I think the Final Answer: is BFS"
        assert parse_final_answer(text) is None

    def test_final_answer_inside_thought_at_line_start(self):
        """Final Answer at line start inside Thought still matches (first wins)."""
        text = (
            "Thought: let me show the format\n"
            "Final Answer: example answer\n"
            "But actually I need more info."
        )
        result = parse_final_answer(text)
        assert result is not None
        assert "example answer" in result
