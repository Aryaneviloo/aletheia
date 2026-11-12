"""Extractor fixes that used to crash the ingestion worker."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_INGEST = _ROOT / "services" / "ingestion-worker"


def test_html_extractor_strips_script_and_keeps_text():
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_INGEST)
    env.setdefault(
        "DATABASE_URL",
        "postgresql+psycopg://aletheia:changeme@localhost:5433/aletheia",
    )
    script = """
from app.extractors.html import HTMLExtractor
html = "<html><body><script>ignore()</script><p>Keep this</p></body></html>"
text = HTMLExtractor().extract(html)
assert "Keep this" in text, text
assert "ignore" not in text, text
"""
    subprocess.check_call([sys.executable, "-c", script], cwd=_ROOT, env=env)


def test_pdf_page_break_matches_chunker():
    pdf_source = (_INGEST / "app" / "extractors" / "pdf.py").read_text()
    chunker_source = (_INGEST / "app" / "chunker.py").read_text()
    marker = "---PAGE BREAK---"
    assert marker in pdf_source
    assert marker in chunker_source
    assert "------PAGE BREAK-------" not in pdf_source
    assert "re.sun" not in (_INGEST / "app" / "extractors" / "html.py").read_text()
