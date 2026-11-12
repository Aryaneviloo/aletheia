"""Unit tests for the token-aware recursive chunker."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_INGEST = Path(__file__).resolve().parents[2] / "services" / "ingestion-worker"


def _load(module_name: str, relative: str):
    path = _INGEST / relative
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


chunk_text = _load("aletheia_chunker_under_test", "app/chunker.py").chunk_text
compute_content_hash = _load("aletheia_hashing_under_test", "app/hashing.py").compute_content_hash


def test_short_text_single_chunk():
    """Text under chunk size tokens should produce exactly one chunk."""
    text = "This is a test"
    chunks = chunk_text(text)
    assert len(chunks) == 1
    assert chunks[0].content == text.strip()
    assert chunks[0].chunk_index == 0


def test_empty_text_no_chunks():
    assert chunk_text("  ") == []


def test_chunk_has_token_count():
    chunks = chunk_text("Vector databases store embeddings for fast similarity search.")
    assert all(c.token_count > 0 for c in chunks)


def test_chunk_index_sequential():
    text = "This is a sentence about vector search. " * 50
    chunks = chunk_text(text)
    indices = [c.chunk_index for c in chunks]
    assert indices == list(range(len(chunks)))


def test_content_hash_deterministic():
    text = "hello world"
    assert compute_content_hash(text) == compute_content_hash(text)


def test_content_hash_different_for_different_content():
    assert compute_content_hash("hello") != compute_content_hash("world")
