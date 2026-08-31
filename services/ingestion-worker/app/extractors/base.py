"""
ingestion_worker.app.extractors.base
======================================

Abstract base class for all doc extractor

Adding a new format: 
Create a new file in extractors that subclasses BaseExtractor 
Register it in extractors/__init__py Registery
"""

from __future__ import annotations
import abc


class BaseExtractor(abc.ABC):
    """
    Every extractor implements: extract()
    Input is raw content (str or bytes)
    Output is clean plain text 
    """

    @abc.abstractmethod
    def extract(self, content: str | bytes) -> str:
        """ 
        Extract plain text from raw content
        """
        ...

    @property
    @abc.abstractmethod
    def supported_mime_types(self) -> list[str]
    """ MIME types the extractor handles"""
    ...