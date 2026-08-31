"""
ingestion_worker.app.hashing
=============================

Content hashing for idempotent ingestion
SHA-256 is computes at two places:
 - ingestion.py to check for duplicates before creating the doc row
 - in the worker to verify the content hasnt changed 
 
"""

from __future__ import annotations
import hashlib

def compute_content_hash(content: str) -> str:

    """
    SHA - 256 hash of content, UTF-8 encoded returned as hex string
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
