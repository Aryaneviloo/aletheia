"""
Extractor registry maps MIME types to extractor instances.

ADD new formats here: instantiate the extractor and add its
supported_mime_types to the registry dict.

"""

from __future__ import annotations
from app.extractors.base import BaseExtractor
from app.extractors.html import HTMLExtractor
from app.extractors.pdf import PDFExtractor
from app.extractors.text import PlainTextExtractor

_plain = PlainTextExtractor()
_html = HTMLExtractor()
_pdf = PDFExtractor()


#REgistry: mime types -> extrctor instance

EXTRACTION_REGISTRY: dict[str, BaseExtractor] = {}

for extractor in [_plain, _html, _pdf]:
    for mime_type in extractor.supported_mime_types:
        EXTRACTION_REGISTRY[mime_type] = extractor


def get_extractor(mime_types: str) -> BaseExtractor:
    """
    Returns the extractor for a given MIME type
    Falls back to Plain Text for unknown types
    """
    return EXTRACTION_REGISTRY.get(mime_type, _plain)
