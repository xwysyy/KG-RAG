"""Tests for kg_rag.ingest.chunking."""

import pytest
from kg_rag.ingest.chunking import chunk_by_tokens


class TestChunkByTokens:
    def test_empty_text(self):
        assert chunk_by_tokens("") == []

    def test_single_chunk(self):
        chunks = chunk_by_tokens("hello world", chunk_size=100, overlap=0)
        assert len(chunks) == 1
        assert "hello world" in chunks[0].content

    def test_overlap_zero_respected(self):
        """Regression: overlap=0 must not fall back to default."""
        chunks = chunk_by_tokens("hello world", chunk_size=100, overlap=0)
        assert len(chunks) == 1

    def test_multiple_chunks(self):
        text = " ".join(["word"] * 200)
        chunks = chunk_by_tokens(text, chunk_size=50, overlap=10)
        assert len(chunks) > 1

    def test_overlap_creates_redundancy(self):
        text = " ".join(["word"] * 200)
        no_overlap = chunk_by_tokens(text, chunk_size=50, overlap=0)
        with_overlap = chunk_by_tokens(text, chunk_size=50, overlap=10)
        assert len(with_overlap) > len(no_overlap)

    def test_chunk_ids_unique(self):
        text = " ".join(["word"] * 200)
        chunks = chunk_by_tokens(text, doc_id="doc1", chunk_size=50, overlap=10)
        ids = [c.id for c in chunks]
        assert len(ids) == len(set(ids))

    def test_doc_id_propagated(self):
        chunks = chunk_by_tokens("hello", doc_id="mydoc", chunk_size=100, overlap=0)
        assert chunks[0].doc_id == "mydoc"

    def test_metadata_has_token_offsets(self):
        chunks = chunk_by_tokens("hello world", chunk_size=100, overlap=0)
        assert "token_start" in chunks[0].metadata
        assert "token_end" in chunks[0].metadata

    def test_invalid_chunk_size(self):
        with pytest.raises(ValueError, match="chunk_size must be positive"):
            chunk_by_tokens("hello", chunk_size=0, overlap=0)

    def test_overlap_exceeds_chunk_size(self):
        with pytest.raises(ValueError, match="overlap must be in"):
            chunk_by_tokens("hello", chunk_size=10, overlap=10)
