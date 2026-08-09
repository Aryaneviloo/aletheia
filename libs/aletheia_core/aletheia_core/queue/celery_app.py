"""
aletheia_core.queue.celery_app
====================================

The single Celery application instance shared across every service in
Aletheia swarm

Usage
-----
    # In a worker service (e.g. ingestion-worker/app/celery_worker.py):
    from aletheia_core.queue.celery_app import celery_app, Queues

    # Tasks are registered by decorating functions with @celery_app.task
    # in the worker's own tasks.py — not here.

    # In the gateway (dispatching work):
    from aletheia_core.queue.celery_app import celery_app, Queues

    result = celery_app.send_task(
        "ingestion.process_document",
        args=[str(document_id)],
        queue=Queues.INGESTION,
    )
"""

from __future__ import annotations

from celery import Celery

from aletheia_core.config import get_settings



class Queues:
    """
    Centralized queue name constants
    TO avoid a typo in queue name
    """

    INGESTION: str = "ingestion"
    SYNTHESIS: str = "synthesis"
    JUDGE: str = "judge"

def create_celery_app() -> Celery:
    """
    Build and configure the Celery application
    Called once at module level
    """
    settings = get_settings()

    app = Celery(
        "aletheia",
        broker=str(settings.redis_url),
        backend=str(settings.redis_url),
    )

    app.conf.update(
        #-------Serialization--------
        #JSON instead of pickle
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],

        # -------Routing ----------
        #default queue for tasks for a safety net
        task_default_queue=Queues.INGESTION,

        #how long the task results stay 
        result_expires=86400,

        #only acknowledge a task when it is done 
        task_acks_late=True,
        task_reject_on_worker_lost = True,

        timezone = "UTC",
        enable_utc = True,
    )

    return app

celery_app = create_celery_app()