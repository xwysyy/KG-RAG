"""NanoVectorDB-backed vector store implementation."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import numpy as np
from langchain_openai import OpenAIEmbeddings
from nano_vectordb import NanoVectorDB

from kg_rag.config import settings
from kg_rag.storage.base import BaseVectorStore

logger = logging.getLogger(__name__)

_EN_TOKEN_RE = re.compile(r"[A-Za-z]{2,16}")
_ZH_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]{3,16}")

_STOP_EN = {
    # common tracing / debugging tokens (avoid polluting retrieval when users paste logs/markers)
    "trace",
    "check",
    "marker",
    "langsmith",
    "langchain",
}


def _extract_keywords(query: str, *, max_each: int = 8) -> tuple[list[str], list[str]]:
    """Extract a small set of deterministic keywords for lexical boosting.

    This is a lightweight complement to vector similarity when embeddings are
    noisy or the query contains distinctive aliases like BFS/DFS.
    """
    en_seen: set[str] = set()
    zh_seen: set[str] = set()
    en: list[str] = []
    zh: list[str] = []

    for tok in _EN_TOKEN_RE.findall(query):
        low = tok.lower()
        if low in _STOP_EN:
            continue
        if low in en_seen:
            continue
        en_seen.add(low)
        en.append(low)
        if len(en) >= max_each:
            break

    for tok in _ZH_TOKEN_RE.findall(query):
        if tok in zh_seen:
            continue
        zh_seen.add(tok)
        zh.append(tok)
        if len(zh) >= max_each:
            break

    return en, zh


def _keyword_score(content: str, en: list[str], zh: list[str]) -> int:
    if not content or (not en and not zh):
        return 0
    c_lower = content.lower()
    score = 0
    for k in en:
        score += c_lower.count(k)
    for k in zh:
        score += content.count(k)
    return score


def _query_with_lexical_boost(
    db: NanoVectorDB,
    qvec: np.ndarray,
    *,
    top_k: int,
    en_keywords: list[str],
    zh_keywords: list[str],
) -> list[dict[str, Any]]:
    """Query NanoVectorDB and re-rank with a deterministic lexical signal.

    This keeps the system agentic (no forced routing), but makes vector_search
    more reliable for acronym-heavy queries where exact matches are expected.
    """
    storage = db._NanoVectorDB__storage  # noqa: SLF001
    data = storage.get("data", [])
    mat = storage.get("matrix")
    if not data or mat is None or len(data) == 0:
        return []

    # Cosine similarity: stored vectors are normalized in nano-vectordb pre_process.
    denom = float(np.linalg.norm(qvec)) or 1.0
    q = (qvec / denom).astype(np.float32, copy=False)
    scores = mat @ q

    n = len(data)
    k = max(0, min(int(top_k), n))
    if k == 0:
        return []

    order_by_score = np.argsort(scores)[::-1]

    keyword_scores: list[int] | None = None
    selected: list[int] = []
    seen: set[int] = set()

    if en_keywords or zh_keywords:
        keyword_scores = [
            _keyword_score(rec.get("content", ""), en_keywords, zh_keywords)
            for rec in data
        ]
        hit_idxs = [i for i, s in enumerate(keyword_scores) if s > 0]
        if hit_idxs:
            hit_idxs.sort(
                key=lambda i: (keyword_scores[i], float(scores[i])), reverse=True
            )
            for i in hit_idxs:
                selected.append(i)
                seen.add(i)
                if len(selected) >= k:
                    break

    if len(selected) < k:
        for idx in order_by_score:
            i = int(idx)
            if i in seen:
                continue
            selected.append(i)
            if len(selected) >= k:
                break

    results: list[dict[str, Any]] = []
    for i in selected:
        rec = data[i]
        rid = rec.get("__id__", "")
        content = rec.get("content", "")
        meta = {k: v for k, v in rec.items() if k not in ("__id__", "content")}
        if keyword_scores is not None:
            meta["keyword_score"] = int(keyword_scores[i])
        results.append(
            {
                "id": rid,
                "distance": float(scores[i]),
                "content": content,
                "metadata": meta,
            }
        )

    return results


class NanoVectorStore(BaseVectorStore):
    """Thin wrapper around NanoVectorDB with OpenAI-compatible embeddings."""

    def __init__(self, persist_path: str | None = None) -> None:
        self._persist_path = persist_path or str(
            settings.data_dir / "nano_vector.json"
        )
        self._embedding = OpenAIEmbeddings(
            model=settings.embedding_model,
            openai_api_key=settings.embedding_api_key,
            openai_api_base=settings.embedding_base_url,
        )
        self._db = NanoVectorDB(
            embedding_dim=settings.embedding_dim,
            storage_file=self._persist_path,
        )
        self._lock = asyncio.Lock()

    # -- BaseVectorStore interface -------------------------------------------

    async def query(
        self,
        query: str,
        top_k: int = 5,
        *,
        query_embedding: list[float] | None = None,
    ) -> list[dict[str, Any]]:
        if query_embedding is None:
            query_embedding = await self._embed(query)

        qvec = np.array(query_embedding, dtype=np.float32)
        en_keywords, zh_keywords = _extract_keywords(query)
        async with self._lock:
            return await asyncio.to_thread(
                _query_with_lexical_boost,
                self._db,
                qvec,
                top_k=top_k,
                en_keywords=en_keywords,
                zh_keywords=zh_keywords,
            )

    async def upsert(self, data: dict[str, dict[str, Any]]) -> None:
        if not data:
            return

        ids = list(data.keys())
        contents = [data[i].get("content", "") for i in ids]
        embeddings = await self._embed_batch(contents)

        records = []
        for idx, doc_id in enumerate(ids):
            record = {
                "__id__": doc_id,
                "__vector__": np.array(embeddings[idx], dtype=np.float32),
                "content": contents[idx],
            }
            # attach extra metadata
            for k, v in data[doc_id].items():
                if k != "content":
                    record[k] = v
            records.append(record)

        async with self._lock:
            await asyncio.to_thread(self._db.upsert, records)
            await asyncio.to_thread(self._db.save)
        logger.info("Upserted %d records into NanoVectorDB", len(records))

    async def delete(self, ids: list[str]) -> None:
        async with self._lock:
            await asyncio.to_thread(self._db.delete, ids)
            await asyncio.to_thread(self._db.save)
        logger.info("Deleted %d records from NanoVectorDB", len(ids))

    async def finalize(self) -> None:
        async with self._lock:
            await asyncio.to_thread(self._db.save)

    # -- helpers -------------------------------------------------------------

    async def _embed(self, text: str) -> list[float]:
        return await self._embedding.aembed_query(text)

    async def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        return await self._embedding.aembed_documents(texts)
