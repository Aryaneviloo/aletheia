"""HTML extractor: strips tags """

from __future__ import annotations
from app.extractors.base import BaseExtractor

class HTMLExtractor(BaseExtractor):
    """
    Extracts readable text from html using BeautifulSoup
    Removes scripts and tags
    """

    def extract(self, content: str | bytes) -> str:
        from bs4 import BeautifulSoup

        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="replace")

        soup = BeautifulSoup(content, "html-parser")

        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        #get text with separator preserves block level whitespace

        text = soup.get_text(separator="\n", strip = True)

        import re
        text = re.sun(r'\n{3,}', '\n\n', text)
        return text.strip()

    @property
    def supported_mime_types(self) -> list[str]:
        return ["text/html"]

    