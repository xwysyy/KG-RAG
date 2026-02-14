"""Preprocess OI-wiki MkDocs markdown files for KG ingestion.

Usage:
    python scripts/preprocess.py <input_dir> <output_dir>

Phase 1: mechanical cleanup (regex, no LLM)
Phase 2: LLM-based cleanup (admonitions, tabbed blocks)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import asyncio

import openai
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# ---------------------------------------------------------------------------
# Resolve project root so we can import settings
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from kg_rag.config import settings  # noqa: E402


# ========================== Phase 1: mechanical ============================

_RAW_ROOT = _PROJECT_ROOT / "data" / "raw" / "OI-wiki-master"
_RE_INCLUDE = re.compile(r'^(\s*)--8<--\s*"(.+?)"\s*$', re.MULTILINE)
_RE_IMAGE = re.compile(r"^!\[.*?\]\(images/.*?\)\s*$", re.MULTILINE)


def _resolve_include(match: re.Match) -> str:
    """Replace --8<-- include with actual file content, or remove if missing."""
    indent = match.group(1)
    rel_path = match.group(2)
    code_file = (_RAW_ROOT / rel_path).resolve()
    if not code_file.is_file() or not code_file.is_relative_to(_RAW_ROOT.resolve()):
        return ""  # file not found or path traversal, remove the line
    code = code_file.read_text(encoding="utf-8").rstrip()
    # Re-indent each line to match the original indentation
    indented = "\n".join(indent + line if line else "" for line in code.split("\n"))
    return indented


def phase1(text: str) -> str:
    """Remove author front-matter, inline --8<-- includes, remove images."""
    # Remove author line only if it's the very first line
    lines = text.split("\n")
    if lines and re.match(r"^author:\s", lines[0]):
        lines = lines[1:]
        if lines and lines[0].strip() == "":
            lines = lines[1:]
    text = "\n".join(lines)

    # Inline --8<-- includes with actual code content
    text = _RE_INCLUDE.sub(_resolve_include, text)

    # Remove image lines
    text = _RE_IMAGE.sub("", text)

    # Collapse 3+ consecutive blank lines into 2
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip() + "\n"


# ========================== Phase 2: LLM cleanup ==========================

_SYSTEM_PROMPT = """\
You are a Markdown syntax converter. Convert MkDocs Material admonitions and \
tabbed blocks to standard Markdown. Rules:

1. `???+ type "title"` or `??? type "title"` admonition blocks:
   - Replace the admonition line with a heading: `### title` (or `#### title` \
if already inside a subsection).
   - Un-indent the body content by one level (4 spaces or 1 tab).
   - If the admonition has no explicit title, use the type as title \
(e.g. `??? note` → `### Note`).

2. `=== "label"` tabbed blocks:
   - Remove the `=== "label"` line.
   - Un-indent the body content by one level.
   - If the tab contains a code block, add the label as a comment before it, \
e.g. `<!-- C++ -->`.

3. Preserve ALL other content exactly: LaTeX math ($...$, $$...$$), markdown \
links, footnotes, normal code blocks, lists, and prose.
4. Do NOT add or remove any substantive content.
5. Output ONLY the converted Markdown, no explanations."""


def _build_client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=settings.reasoning_llm_api_key, base_url=settings.reasoning_llm_base_url)


@retry(
    retry=retry_if_exception_type((openai.RateLimitError, openai.APITimeoutError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    reraise=True,
)
async def phase2(
    text: str, client: AsyncOpenAI, sem: asyncio.Semaphore
) -> str | None:
    """Use LLM to convert admonitions and tabbed blocks.

    Returns None if the response was truncated (finish_reason == 'length').
    """
    async with sem:
        resp = await client.chat.completions.create(
            model=settings.reasoning_llm_model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            temperature=0.0,
        )
    # Truncation detection
    if resp.choices[0].finish_reason == "length":
        return None
    content = resp.choices[0].message.content or ""
    # Strip <think>...</think> reasoning tags anchored to start (deepseek-reasoner)
    content = re.sub(r"^\s*<think>[\s\S]*?</think>\s*", "", content)
    # Strip wrapping ```markdown ... ``` only if both opening and closing fences exist
    wrapped = re.match(r"^```(?:markdown|md)\s*\n", content)
    if wrapped and re.search(r"\n```\s*$", content):
        content = content[wrapped.end():]
        content = re.sub(r"\n```\s*$", "", content)
    # Remove DeepSeek watermark
    content = re.sub(r"本回答由 AI 生成.*$", "", content)
    # Collapse 3+ consecutive blank lines into 2
    content = re.sub(r"\n{3,}", "\n\n", content)
    return content.strip() + "\n"


# ========================== CLI entry point ================================

def _needs_llm(text: str) -> bool:
    """Check if text contains admonitions or tabbed blocks that need LLM."""
    return bool(re.search(r"^\?{3}\+?\s", text, re.MULTILINE)) or bool(
        re.search(r'^===\s+"', text, re.MULTILINE)
    )


def _fences_balanced(text: str) -> bool:
    """Check that code fences (``` and ~~~) are properly paired."""
    cnt = sum(
        1 for line in text.splitlines()
        if line.lstrip().startswith("```") or line.lstrip().startswith("~~~")
    )
    return cnt % 2 == 0



async def process_file(
    idx: int,
    total: int,
    path: Path,
    out_name: str,
    out_dir: Path,
    client: AsyncOpenAI,
    sem: asyncio.Semaphore,
) -> bool:
    """Process a single markdown file. Returns True on success."""
    print(f"[{idx}/{total}] {out_name}")
    text = await asyncio.to_thread(path.read_text, encoding="utf-8")

    # Phase 1 (includes sync file reads in _resolve_include, wrapped by to_thread)
    text = await asyncio.to_thread(phase1, text)
    phase1_text = text  # keep as fallback

    # Phase 2 — only call LLM if needed
    if _needs_llm(text):
        try:
            result = await phase2(text, client, sem)
        except Exception as exc:
            print(f"  WARN: Phase 2 failed for {out_name}: {exc}, using Phase 1 result")
            text = phase1_text
        else:
            if result is None:
                print(f"  WARN: LLM output truncated for {out_name}, using Phase 1 result")
                text = phase1_text
            elif not _fences_balanced(result):
                print(f"  WARN: LLM output has unbalanced fences for {out_name}, using Phase 1 result")
                text = phase1_text
            else:
                text = result

    out_dir.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread((out_dir / out_name).write_text, text, encoding="utf-8")
    return True


def _make_out_name(path: Path, base_dir: Path) -> str:
    """Build collision-safe output filename from relative path.

    e.g. docs/misc/offline.md → misc--offline.md
         docs/index.md        → index.md
    """
    rel = path.relative_to(base_dir)
    parts = list(rel.parts)
    return "--".join(parts) if len(parts) > 1 else parts[0]


async def amain() -> None:
    if len(sys.argv) != 3:
        print(f"Usage: python {sys.argv[0]} <input_dir> <output_dir>")
        sys.exit(1)

    in_dir = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])

    if not in_dir.is_dir():
        print(f"Error: {in_dir} is not a directory")
        sys.exit(1)

    files = sorted(in_dir.rglob("*.md"))
    if not files:
        print(f"No .md files found in {in_dir}")
        sys.exit(1)

    out_names = [_make_out_name(f, in_dir) for f in files]
    print(f"Found {len(files)} .md files (recursive)")

    client = _build_client()
    sem = asyncio.Semaphore(settings.llm_concurrency)

    tasks = [
        process_file(i, len(files), f, name, out_dir, client, sem)
        for i, (f, name) in enumerate(zip(files, out_names), 1)
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    ok = sum(1 for r in results if r is True)
    fail = sum(1 for r in results if r is not True)
    for f, r in zip(files, results):
        if isinstance(r, Exception):
            print(f"  FAILED {f.name}: {r}")

    print(f"\nDone: {ok} succeeded, {fail} failed")


if __name__ == "__main__":
    asyncio.run(amain())
