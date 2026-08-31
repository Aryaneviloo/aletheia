"""
ingestion_worker.app.tasks
============================

The ingestion Celery task — the core of the entire ingestion pipeline.

Pipeline:
  1. Load Document from Postgres, validate it's still pending
  2. Extract text (plain/PDF/HTML via extractor registry)
  3. Chunk text (token-aware, recursive)
  4. Embed all chunks in one batch call to inference-service
  5. Write Chunk rows to Postgres
  6. Upsert vectors to Qdrant
  7. Update Document.status and Job.status to completed
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import httpx
from celery import Task
from celery.utils.log import get_task_logger

from aletheia_core.config import get_settings
from aletheia_core.db.base import session_scope
from aletheia_core.db.models import (
    Chunk,
    Document,
    DocumentStatus,
    Job,
    JobStatus,
)
from aletheia_core.queue.celery_app import celery_app
from aletheia_core.vector.client import ChunkPoint, get_vector_store
from app.chunker import chunk_text
from app.extractors import get_extractor

log = get_task_logger(__name__)


def _embed_chunks(texts: list[str]) -> list[list[float]]:
    """
    Embed a batch of texts via inference-service /embed.
    One HTTP call for the whole batch — not one per chunk.
    """
    settings = get_settings()
    response = httpx.post(
        f"{settings.inference_service_url}/embed",
        json={"texts": texts},
        timeout=120.0,
    )
    response.raise_for_status()
    return response.json()["embeddings"]


@celery_app.task(
    name="ingestion.process_document",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
)
def process_document(
    self: Task,
    document_id: str,
    job_id: str,
    content: str | None,
    source_url: str | None,
) -> dict:
    """
    Full ingestion pipeline for one document.

    Returns a result dict that gets stored in both the Celery result
    backend (Redis) and the Job.result column (Postgres).
    """
    doc_uuid = uuid.UUID(document_id)
    job_uuid = uuid.UUID(job_id)
    settings = get_settings()

    log.info(f"Starting ingestion for document {document_id}")

    try:
        # --- Step 1: Load document, mark as processing ---
        with session_scope() as db:
            document = db.get(Document, doc_uuid)
            if not document:
                log.error(f"Document {document_id} not found — task cancelled")
                return {"error": "document_not_found"}

            if document.status != DocumentStatus.PENDING:
                log.warning(f"Document {document_id} is not pending (status={document.status}), skipping")
                return {"skipped": True, "status": str(document.status)}

            document.status = DocumentStatus.PROCESSING
            collection_id = document.collection_id

        # --- Step 2: Extract text ---
        # Content was passed directly from the gateway for text ingestion.
        # URL-based ingestion fetches the content here.
        if content:
            raw_text = content
            mime_type = "text/plain"
        elif source_url:
            log.info(f"Fetching content from {source_url}")
            response = httpx.get(source_url, timeout=30.0, follow_redirects=True)
            response.raise_for_status()
            raw_text = response.text
            mime_type = response.headers.get("content-type", "text/plain").split(";")[0]
        else:
            raise ValueError("No content or source_url provided")

        extractor = get_extractor(mime_type)
        extracted_text = extractor.extract(raw_text)

        if not extracted_text.strip():
            raise ValueError("Extraction produced empty content")

        # --- Step 3: Chunk ---
        chunks = chunk_text(extracted_text)
        log.info(f"Document {document_id} produced {len(chunks)} chunks")

        if not chunks:
            raise ValueError("Chunking produced no chunks")

        # --- Step 4: Embed all chunks in one batch ---
        try:
            embeddings = _embed_chunks([c.content for c in chunks])
        except httpx.HTTPError as e:
            log.warning(f"Embedding failed, retrying: {e}")
            raise self.retry(exc=e)

        # --- Step 5: Write Chunk rows to Postgres ---
        chunk_rows = []
        with session_scope() as db:
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                qdrant_point_id = uuid.uuid4()
                chunk_row = Chunk(
                    document_id=doc_uuid,
                    collection_id=collection_id,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    token_count=chunk.token_count,
                    embedding_model=settings.embedding_model_name,
                    embedding_dim=len(embedding),
                    qdrant_point_id=qdrant_point_id,
                )
                db.add(chunk_row)
                chunk_rows.append((chunk_row, embedding, qdrant_point_id))
            # flush assigns IDs without committing
            db.flush()
            chunk_data = [
                (c.id, c.document_id, c.collection_id, emb, qid)
                for c, emb, qid in chunk_rows
            ]
            db.commit()

        # --- Step 6: Upsert vectors to Qdrant ---
        vector_store = get_vector_store()
        vector_store.ensure_collection()
        vector_store.upsert_chunks([
            ChunkPoint(
                point_id=qid,
                vector=emb,
                chunk_id=cid,
                document_id=did,
                collection_id=col_id,
            )
            for cid, did, col_id, emb, qid in chunk_data
        ])

        # --- Step 7: Mark document and job as completed ---
        result = {
            "document_id": document_id,
            "chunk_count": len(chunks),
            "embedding_model": settings.embedding_model_name,
        }

        with session_scope() as db:
            document = db.get(Document, doc_uuid)
            if document:
                document.status = DocumentStatus.COMPLETED

            job = db.get(Job, job_uuid)
            if job:
                job.status = JobStatus.COMPLETED
                job.result = result

        log.info(f"Ingestion complete: {len(chunks)} chunks for document {document_id}")
        return result

    except Exception as exc:
        log.error(f"Ingestion failed for document {document_id}: {exc}")

        # Mark both document and job as failed
        with session_scope() as db:
            document = db.get(Document, doc_uuid)
            if document:
                document.status = DocumentStatus.FAILED
                document.error_message = str(exc)

            job = db.get(Job, job_uuid)
            if job:
                job.status = JobStatus.FAILED
                job.error_message = str(exc)

        raise