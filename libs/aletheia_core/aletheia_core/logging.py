"""
aletheia_core.logging
======================

Structured, JSON-capable logging shared by every Aletheia service.


This module has two ideas:

  1. Every log line carries a `request_id` (HTTP requests) or `job_id`
     (Celery tasks), bound once via `bind_request_id()` / `bind_job_id()`
     and then automatically attached to every subsequent log call in
     that context via Python's `contextvars`, not by threading an ID
     through every function signature by hand.
  2. Output format depends on environment: human-readable, colored
     console output locally; single-line JSON in staging/production,

Usage
-----
    # once, at service startup (FastAPI lifespan, or top of celery_worker.py):
    from aletheia_core.config import get_settings
    from aletheia_core.logging import configure_logging

    configure_logging(get_settings())

    # anywhere else, at the top of any module:
    from aletheia_core.logging import get_logger

    log = get_logger(__name__)
    log.info("document_ingested", document_id=str(doc.id), chunk_count=12)

    # at the top of a request or task, to correlate everything downstream:
    from aletheia_core.logging import bind_request_id

    bind_request_id(request_id)
"""

from __future__ import annotations

import logging
import sys
import uuid

import structlog
from structlog.types import Processor

from aletheia_core.config import Settings


def bind_request_id(request_id: str | None = None) -> str:
    """
    Bind a request_id to the current context (HTTP request lifecycle).
    Generates a new UUID4 if one isn't provided
    """
    rid = request_id or str(uuid.uuid4())
    structlog.contextvars.bind_contextvars(request_id=rid)
    return rid


def bind_job_id(job_id: str, task_name: str | None = None) -> None:
    """
    Bind a job_id (and optionally the Celery task name) to the current
    context. Call this at the top of every Celery task body.
    """
    structlog.contextvars.bind_contextvars(job_id=job_id, task_name=task_name)


def clear_context() -> None:
    """
    Clear bound context vars.
    """
    structlog.contextvars.clear_contextvars()


# --- Configuration -------------------------------------------------------

def configure_logging(settings: Settings) -> None:
    """
    Configure structlog + stdlib logging for the current process.
    """
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    renderer: Processor = (
        structlog.dev.ConsoleRenderer(colors=True)
        if settings.environment == "local"
        else structlog.processors.JSONRenderer()
    )

    structlog.configure(
        processors=shared_processors + [structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    formatter = structlog.stdlib.ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=shared_processors,
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(settings.log_level)

    for noisy in ("sqlalchemy.engine", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(
            logging.WARNING if settings.log_level != "DEBUG" else logging.DEBUG
        )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """
    Get a structured logger bound to a module name.
    """
    return structlog.get_logger(name)