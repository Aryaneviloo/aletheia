


"""Unit tests for the token-aware recursive chunker."""

from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../services/ingestion-worker"))

from app.chunker import chunk_text


def test_short_text_single_chunk():
    """Text under chunk size tokens should produce exactly one chunk"""
    text = "This is a test"
    chunks = chunk_text(text)
    assert len(chunks) == 1
    assert chunks[0].content == text.strip()
    assert chunks[0].chunk_index == 0


def test_empty_text_no_chunks():
    chunks = chunk_text("  ")
    assert chunks == []


def test_chunk_has_token_count():
    chunks = chunk_text("Vector databases store embeddings for fast similarity search.")
    assert all(c.token_count > 0 for c in chunks)


def test_chunk_index_sequential():
    # Generate enough text to produce multiple chunks
    text = ("This is a sentence about vector search. " * 50)
    chunks = chunk_text(text)
    indices = [c.chunk_index for c in chunks]
    assert indices == list(range(len(chunks)))


def test_content_hash_deterministic():
    """Same content always produces same hash."""
    from app.hashing import compute_content_hash
    text = "hello world"
    assert compute_content_hash(text) == compute_content_hash(text)




def test_content_hash_different_for_different_content():
    from app.hashing import compute_content_hash
    assert compute_content_hash("hello") != compute_content_hash("world")