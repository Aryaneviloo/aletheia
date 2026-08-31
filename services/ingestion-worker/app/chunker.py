"""
ingestion_worker.app.chunker
==============================

Token-aware recursive chunker.
  1. Uses tiktoken to count real tokens (what LLMs actually measure)
  2. Recursively splits on increasingly fine boundaries:
     paragraphs → newlines → sentences → hard token cut
  3. Overlaps adjacent chunks by `overlap_tokens` so context isn't
     lost at chunk boundaries — a sentence split across chunks is
     fully present in both.

"""

from __future__ import annotations

import re
from dataclasses import dataclass

import tiktoken

from aletheia_core.config import get_settings
from aletheia_core.logging import get_logger

log = get_logger(__name__)

# Use cl100k_base — the tokenizer for GPT-4/3.5 and a reasonable
# approximation for most modern LLMs 
_TOKENIZER = tiktoken.get_encoding("cl100k_base")


@dataclass
class Chunk:
    """One chunk of text with its token count and position in the document."""
    content: str
    token_count: int
    chunk_index: int


def _count_tokens(text: str) -> int:
    return len(_TOKENIZER.encode(text))


def _split_text_recursive(
    text: str,
    chunk_size: int,
    overlap: int,
    separators: list[str],
) -> list[str]:
    """
    Recursively split text using progressively finer separators until
    every piece fits within chunk_size tokens.
    """
    if _count_tokens(text) <= chunk_size:
        return [text] if text.strip() else []

    if not separators:
        # Last resort: hard split by tokens
        tokens = _TOKENIZER.encode(text)
        pieces = []
        start = 0
        while start < len(tokens):
            end = min(start + chunk_size, len(tokens))
            piece = _TOKENIZER.decode(tokens[start:end])
            pieces.append(piece)
            start += chunk_size - overlap
        return pieces

    separator = separators[0]
    remaining_separators = separators[1:]

    parts = text.split(separator)
    chunks: list[str] = []
    current = ""

    for part in parts:
        candidate = (current + separator + part).strip() if current else part.strip()
        if _count_tokens(candidate) <= chunk_size:
            current = candidate
        else:
            if current:
                chunks.extend(
                    _split_text_recursive(current, chunk_size, overlap, remaining_separators)
                )
            current = part.strip()

    if current:
        chunks.extend(
            _split_text_recursive(current, chunk_size, overlap, remaining_separators)
        )

    return chunks


def chunk_text(text: str) -> list[Chunk]:
    """
    Chunk a document's text into overlapping, token-sized pieces.
    Returns an ordered list of Chunk objects with their token counts
    and position indices.
    """
    settings = get_settings()
    chunk_size = settings.chunk_size_tokens
    overlap = settings.chunk_overlap_tokens

    separators = [
        "\n\n---PAGE BREAK---\n\n",  # PDF page boundaries
        "\n\n",                       # Paragraph breaks
        "\n",                         # Line breaks
        ". ",                         # Sentence boundaries
        " ",                          # Word boundaries (last resort before hard cut)
    ]

    raw_chunks = _split_text_recursive(text, chunk_size, overlap, separators)

    # Add overlap between adjacent chunks
    overlapped: list[str] = []
    for i, chunk in enumerate(raw_chunks):
        if i == 0:
            overlapped.append(chunk)
        else:
            prev_tokens = _TOKENIZER.encode(raw_chunks[i - 1])
            overlap_text = _TOKENIZER.decode(prev_tokens[-overlap:]) if len(prev_tokens) > overlap else raw_chunks[i - 1]
            overlapped.append((overlap_text + " " + chunk).strip())

    return [
        Chunk(
            content=c,
            token_count=_count_tokens(c),
            chunk_index=i,
        )
        for i, c in enumerate(overlapped)
        if c.strip()
    ]