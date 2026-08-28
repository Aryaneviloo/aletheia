"""
api_gateway.app.routers.ingestion
==================================
Document ingestion accepts content or URL, creates a Doc row 
in POstgres, dispatches async CELEry task to the ingestion worker

The gateway's role here is:
  1. Validate the request and confirm collection ownership
  2. Compute content_hash for idempotency
  3. Create Document row (status=pending) + Job row in Postgres
  4. Dispatch Celery task with the document_id
  5. Return job_id — client polls /jobs/{job_id} for status
"""

from __future__ import annotations
import hashlib

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from aletheia_core.db.base import get_db
from aletheia_core.db.models import Document, DocumentStatus, Job, JobStatus, JobType, User
from aletheia_core.exceptions import ConflictError, NotFoundError, ValidationError
from aletheia_core.queue.celery_app import Queues, celery_app
from aletheia_core.schemas.ingestion import DocumentIngestRequest, DocumentRead, IngestResponse
from app.dependencies import get_current_user
from app.routers.collections import _get_owned_collection


router = APIRouter(prefix="/ingestion", tags=["ingestion"])


def _compute_content_hash(content: str) -> str:
    """
    SHA-256 hash of the raw content string
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


@router.post("", response_model=IngestResponse, status_code=status.HTTP_202_ACCEPTED)
def ingest_document(
    payload: DocumentIngestRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> IngestResponse:
    """
    Accept a document for ingestion. Returns 202 accepted immediately
    the actual processing is async. Poll GET /job/{job_id} for status
    """

    #Validate content XOR source_url
    if not payload.content and not payload.source_url:
        raise ValidationError(
            message="Either 'content' or 'source_url' must be provided",
            error_code="ingestion_ambiguos_source",
        )

    #confirm the user owns this collection
    _get_owned_collection(payload.collection_id, current_user, db)

     # For URL-based ingestion, the worker fetches the real content —
    # we hash the URL itself as a "this URL was already ingested" check.
    hash_source = payload.content or str(payload.source_url)
    content_hash = _compute_content_hash(hash_source)


    #check for duplicate before the DB constraint catches it

    existing = db.query(Document).filter(
        Document.collection_id == payload.collection_id,
        Document.content_hash == content_hash,
    ).first()
    if existing:
        raise ConflictError(
            message="This content has already been ingested into the collection.",
            error_code="document_already_exists",
        )

    #Create the document row immediately
    document = Document(
        collection_id = payload.collection_id,
        source_name = payload.source_name,
        source_url = str(payload.source_url) if payload.source_url else None,
        content_hash = content_hash,
        status = DocumentStatus.PENDING,
    )
    db.add(document)
    db.flush()

    #create the job row
    job = Job(
        user_id = current_user.id,
        job_type = JobType.INGESTION,
        status = JobStatus.PENDING,
    )

    db.add(job)
    db.commit ()

     # Dispatch to the ingestion worker — sends a message to Redis,
    # the worker picks it up asynchronously.

    task = celery_app.send_task(
        "ingestion.process_document",
        kwargs={
            "document_id": str(document.id),
            "job_id": str(job.id),
            "content": payload.content,
            "source_url": str(payload.source_url) if payload.source_url else None,
        },
        queue=Queues.INGESTION,
    )

    #store the celery task ID to check live status
    job.celery_task_id = task.id
    db.commit()

    return IngestResponse(
        job_id = job.id,
        document_id=document.id,
        status="accepted",
    )


@router.get("/documents/{document_id}", response_model=DocumentRead)
def get_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Document:
    """
    Get a single document's metadata and current ingestion status
    """
    document = db.get(Document, document_id)
    if not document: 
        raise NotFoundError(
            message=f"Document {document_id} not found.",
            error_code="document_not_found",
        )

    #verificaion throuth the parent colletion
    _get_owned_collection(document.collection_id, current_user, db)
    return document

