"""Shared text utilities."""

from __future__ import annotations

import re
from dataclasses import dataclass


def strip_code_fences(text: str) -> str:
    """Remove markdown code fence lines (``` ...) from *text*.

    Lines whose stripped content starts with ``` are dropped entirely.
    All other lines are preserved unchanged.
    """
    if "```" not in text:
        return text
    lines = text.split("\n")
    return "\n".join(l for l in lines if not l.strip().startswith("```"))


# ---------------------------------------------------------------------------
# ReAct text parsing helpers
# ---------------------------------------------------------------------------

@dataclass
class ReActAction:
    """Parsed Action + Action Input from a ReAct-style LLM response."""
    tool: str
    tool_input: str


_ACTION_RE = re.compile(
    r"^Action\s*:\s*(?P<tool>.+?)\s*(?:\n\s*|\s+)"
    r"Action\s*Input\s*:\s*(?P<input>[^\n\r]+)",
    re.MULTILINE | re.IGNORECASE,
)
_FINAL_ANSWER_RE = re.compile(
    r"^Final\s*Answer\s*:\s*(?P<answer>.*?)(?=\n(?:Thought|Action|Observation)\s*:|\Z)",
    re.MULTILINE | re.DOTALL | re.IGNORECASE,
)


def parse_react_action(
    text: str,
    *,
    allowed_tools: set[str] | None = None,
) -> ReActAction | None:
    """Extract ``Action`` and ``Action Input`` from LLM output.

    If multiple Action blocks are present (e.g. the model echoes a formatting
    example before the real tool call), prefer the last action. When
    *allowed_tools* is provided, prefer the last action whose tool name is in
    that set.

    Returns *None* when the text does not contain a valid action block.
    """
    matches = list(_ACTION_RE.finditer(text))
    if not matches:
        return None

    if allowed_tools:
        for m in reversed(matches):
            tool = m.group("tool").strip()
            if tool in allowed_tools:
                return ReActAction(tool=tool, tool_input=m.group("input").strip())

    m = matches[-1]
    return ReActAction(tool=m.group("tool").strip(), tool_input=m.group("input").strip())


def parse_final_answer(text: str) -> str | None:
    """Extract ``Final Answer`` from LLM output.

    Returns *None* when no final answer marker is found.
    """
    m = _FINAL_ANSWER_RE.search(text)
    if m is None:
        return None
    return m.group("answer").strip()
