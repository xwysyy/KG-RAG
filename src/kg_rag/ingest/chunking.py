"""Text chunking utilities using tiktoken for token-aware splitting."""

from __future__ import annotations

import hashlib
import logging

import tiktoken

from kg_rag.config import settings
from kg_rag.models import TextChunk

logger = logging.getLogger(__name__)

# Use cl100k_base (GPT-4 / text-embedding-3 family)
_enc = tiktoken.get_encoding("cl100k_base")


def _make_chunk_id(doc_id: str, index: int) -> str:
    raw = f"{doc_id}::{index}"
    return hashlib.sha256(raw.encode()).hexdigest()


def chunk_by_tokens(
    text: str,
    doc_id: str = "",
    chunk_size: int | None = None,
    overlap: int | None = None,
) -> list[TextChunk]:
    """Split *text* into token-aware chunks with overlap.

    Parameters
    ----------
    text:
        The full document text.
    doc_id:
        An identifier for the source document.
    chunk_size:
        Max tokens per chunk (defaults to ``settings.chunk_size``).
    overlap:
        Token overlap between consecutive chunks
        (defaults to ``settings.chunk_overlap``).

    Returns
    -------
    A list of ``TextChunk`` objects.
    """
    chunk_size = chunk_size if chunk_size is not None else settings.chunk_size
    overlap = overlap if overlap is not None else settings.chunk_overlap

    if chunk_size <= 0:
        raise ValueError(f"chunk_size must be positive, got {chunk_size}")
    if not (0 <= overlap < chunk_size):
        raise ValueError(
            f"overlap must be in [0, chunk_size), got overlap={overlap}, chunk_size={chunk_size}"
        )

    tokens = _enc.encode(text)
    total = len(tokens)

    if total == 0:
        return []

    chunks: list[TextChunk] = []
    start = 0
    idx = 0

    while start < total:
        end = min(start + chunk_size, total)
        chunk_tokens = tokens[start:end]
        content = _enc.decode(chunk_tokens)

        chunks.append(
            TextChunk(
                id=_make_chunk_id(doc_id, idx),
                content=content,
                doc_id=doc_id,
                metadata={"token_start": start, "token_end": end},
            )
        )

        idx += 1
        start += chunk_size - overlap

    logger.info(
        "Chunked doc %s: %d tokens → %d chunks (size=%d, overlap=%d)",
        doc_id, total, len(chunks), chunk_size, overlap,
    )
    return chunks
