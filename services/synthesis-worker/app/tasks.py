"""
synthesis_worker.app.tasks
============================

Synthesis Celery task — retrieval + generation + judge dispatch.

Fixes from original codebase:
  Bug #2: judge_integrity called with wrong number of args. Fixed.
  Bug #3: retry judge call sent to default queue (deadlock). Fixed —
          always passes queue=Queues.JUDGE explicitly.
  Bug #5: collection filtering compared String == list. Fixed in
          strategist.py which this task calls.
"""

from __future__ import annotations

import json
import uuid

import httpx
from celery import Task
from celery.utils.log import get_task_logger

from aletheia_core.config import get_settings
from aletheia_core.db.base import session_scope
from aletheia_core.db.models import Chunk, Dialogue, Job, JobStatus, Message, MessageRole
from aletheia_core.queue.celery_app import Queues, celery_app
from app.prompts import SYNTHESIS_PROMPT, SYNTHESIS_SYSTEM_PROMPT
from app.strategist import retrieve_candidates

log = get_task_logger(__name__)


def _generate(prompt: str, system_prompt: str) -> str:
    """Call inference-service /generate."""
    settings = get_settings()
    response = httpx.post(
        f"{settings.inference_service_url}/generate",
        json={
            "prompt": prompt,
            "system_prompt": system_prompt,
            "max_tokens": 1024,
            "temperature": 0.3,
        },
        timeout=120.0,
    )
    response.raise_for_status()
    return response.json()["content"]


@celery_app.task(
    name="synthesis.process_synthesis",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    acks_late=True,
)
def process_synthesis(
    self: Task,
    job_id: str,
    user_id: str,
    query: str,
    collection_ids: list[str],
    dialogue_id: str | None = None,
) -> dict:
    """
    Full synthesis pipeline:
      1. Retrieve relevant chunks
      2. Build context string
      3. Generate answer via LLM
      4. Save to Dialogue/Message tables
      5. Dispatch to judge worker for faithfulness scoring
      6. Return result with answer + sources
    """
    job_uuid = uuid.UUID(job_id)
    user_uuid = uuid.UUID(user_id)
    collection_uuids = [uuid.UUID(c) for c in collection_ids]

    log.info(f"Starting synthesis for job {job_id}")

    try:
        # --- Step 1: Retrieve candidates ---
        with session_scope() as db:
            candidates = retrieve_candidates(
                query=query,
                collection_ids=collection_uuids,
                user_id=user_uuid,
                db=db,
                limit=20,
            )

            if not candidates:
                result = {
                    "answer": "No relevant context found for your query.",
                    "sources": [],
                    "job_id": job_id,
                }
                _mark_job(job_uuid, JobStatus.COMPLETED, result)
                return result

            # Load chunk content from Postgres
            chunk_ids = [c.chunk_id for c in candidates[:10]]
            chunks = db.query(Chunk).filter(Chunk.id.in_(chunk_ids)).all()
            chunk_map = {c.id: c for c in chunks}

        # --- Step 2: Build context ---
        context_pieces = []
        sources = []
        for i, candidate in enumerate(candidates[:10]):
            chunk = chunk_map.get(candidate.chunk_id)
            if not chunk:
                continue
            context_pieces.append(f"[{i+1}] {chunk.content}")
            sources.append({
                "chunk_id": str(chunk.id),
                "document_id": str(chunk.document_id),
                "score": candidate.score,
            })

        context = "\n\n".join(context_pieces)

        # --- Step 3: Generate answer ---
        try:
            prompt = SYNTHESIS_PROMPT.format(query=query, context=context)
            answer = _generate(prompt, SYNTHESIS_SYSTEM_PROMPT)
        except httpx.HTTPError as e:
            raise self.retry(exc=e)

        # --- Step 4: Save to Dialogue ---
        with session_scope() as db:
            if dialogue_id:
                dialogue = db.get(Dialogue, uuid.UUID(dialogue_id))
            else:
                dialogue = Dialogue(user_id=user_uuid)
                db.add(dialogue)
                db.flush()

            db.add(Message(
                dialogue_id=dialogue.id,
                role=MessageRole.USER,
                content=query,
            ))
            db.add(Message(
                dialogue_id=dialogue.id,
                role=MessageRole.ASSISTANT,
                content=answer,
            ))
            dialogue_id_str = str(dialogue.id)

        # --- Step 5: Dispatch to judge ---
        # Always pass queue=Queues.JUDGE explicitly — fixes bug #3
        # where the retry call omitted the queue and deadlocked.
        celery_app.send_task(
            "judge.evaluate_answer",
            kwargs={
                "job_id": job_id,
                "query": query,
                "context": context,
                "answer": answer,
            },
            queue=Queues.JUDGE,
        )

        result = {
            "answer": answer,
            "sources": sources,
            "dialogue_id": dialogue_id_str,
            "job_id": job_id,
        }

        _mark_job(job_uuid, JobStatus.COMPLETED, result)
        log.info(f"Synthesis complete for job {job_id}")
        return result

    except Exception as exc:
        log.error(f"Synthesis failed for job {job_id}: {exc}")
        _mark_job(job_uuid, JobStatus.FAILED, error=str(exc))
        raise


def _mark_job(
    job_id: uuid.UUID,
    status: JobStatus,
    result: dict | None = None,
    error: str | None = None,
) -> None:
    with session_scope() as db:
        job = db.get(Job, job_id)
        if job:
            job.status = status
            if result:
                job.result = result
            if error:
                job.error_message = error