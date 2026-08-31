"""Plain text and Markdown extractor"""

from __future__ import annotations
from app.extractors.base import BaseExtractor 

class PlainTextExtractor(BaseExtractor):
    """
    For a plain text and Markdown, strips whitespace and normalizes
    excessive black lines
    """

    def extract(self, content: str | bytes) -> str:
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="replace")

        import re
        content = re.sub(r'\n{3,}', '\n\n', content)
        return content.strip()

    @property
    def supported_mime_types(self) -> list[str]:
        return ["text/plain", "text/markdown"]

    
