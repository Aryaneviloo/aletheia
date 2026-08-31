"""
ingestion_worker.app.extractors.base
======================================

Abstract base class for all document extractors.

An extractor's only job: given raw bytes or a string, return
clean plain text. All the messy format-specific parsing logic
lives in subclasses, not in the task itself.

Adding a new format:
  1. Create a new file in extractors/ that subclasses BaseExtractor
  2. Register it in extractors/__init__.py's EXTRACTOR_REGISTRY
  3. Done — the task picks it up automatically
"""

from __future__ import annotations

import abc


class BaseExtractor(abc.ABC):
    """
    Every extractor implements exactly one method: extract().
    Input is raw content (str or bytes depending on source type).
    Output is always clean plain text — no HTML tags, no PDF artifacts,
    no markdown syntax unless the downstream chunker should see it.
    """

    @abc.abstractmethod
    def extract(self, content: str | bytes) -> str:
        """
        Extract plain text from raw content.
        Should strip formatting artifacts but preserve meaningful
        whitespace (paragraph breaks) for the chunker downstream.
        """
        ...

    @property
    @abc.abstractmethod
    def supported_mime_types(self) -> list[str]:
        """MIME types this extractor handles."""
        ...