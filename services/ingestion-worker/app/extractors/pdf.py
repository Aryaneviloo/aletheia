""" PDF extractor using pypdf"""

from __future__ import annotations
from app.extractors.base import BaseExtractor

class PDFExtractor(BaseExtractor):
    """
    Extracts text from PDF using pypdf. 
    To preserve page boudaries uses separator
    
    LImitation: OCR only pdfs return empty strings
    """

    def extract(self, content: str | bytes) -> str:
        import io
        from pypdf import PdfReader

        if isinstance(content, str):
            content = content.encode("utf-8")

        reader = PdfReader(io.BytesIO(content))

        pages = []
        for page in reader.pages:
            text = page.extract_text() or ""
            if text.strip():
                pages.append(text.strip())


        return "\n\n------PAGE BREAK-------\n\n".join(pages)

    @property
    def supported_mime_types(self) -> list[str]:
        return ["application/pdf"]