"""
ingestion_worker.app.celery_worker
=====================================

Celery worker entry point for the ingestion queue.

Start with:
    celery -A app.celery_worker worker -Q ingestion -c 2 --loglevel=info

-Q ingestion  — only consume from the ingestion queue, not synthesis or judge
-c 2          — 2 concurrent workers (adjust based on available CPU/RAM)
"""

from aletheia_core.config import get_settings
from aletheia_core.logging import configure_logging
from aletheia_core.queue.celery_app import celery_app

# Configure structured logging before anything else
configure_logging(get_settings())

from app import tasks  # noqa: F401, E402

__all__ = ["celery_app"]