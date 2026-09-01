"""
api_gateway.app.routers.synthesis
===================================

Synthesis endpoint — dispatches a synthesis+judge task and returns
a job_id immediately. Client polls /jobs/{job_id} for the answer.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from aletheia_core.db.base import get_db
from aletheia_core.db.models import Job, JobStatus, JobType, User
from aletheia_core.queue.celery_app import Queues, celery_app
from aletheia_core.schemas.jobs import JobRead
from app.dependencies import get_current_user
from app.routers.collections import _get_owned_collection

router = APIRouter(prefix="/synthesis", tags=["synthesis"])


class SynthesisRequest(BaseModel):
    query: str
    collection_ids: list[uuid.UUID]
    dialogue_id: uuid.UUID | None = None


@router.post("", response_model=JobRead, status_code=status.HTTP_202_ACCEPTED)
def synthesize(
    payload: SynthesisRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Job:
    """
    Dispatch a synthesis task
    poll/jobs/{job_id} for the answer once status is 'completed'.
    """
    # Verify collection ownership
    for collection_id in payload.collection_ids:
        _get_owned_collection(collection_id, current_user, db)

    job = Job(
        user_id=current_user.id,
        job_type=JobType.SYNTHESIS,
        status=JobStatus.PENDING,
    )
    db.add(job)
    db.commit()

    task = celery_app.send_task(
        "synthesis.process_synthesis",
        kwargs={
            "job_id": str(job.id),
            "user_id": str(current_user.id),
            "query": payload.query,
            "collection_ids": [str(c) for c in payload.collection_ids],
            "dialogue_id": str(payload.dialogue_id) if payload.dialogue_id else None,
        },
        queue=Queues.SYNTHESIS,
    )

    job.celery_task_id = task.id
    db.commit()
    db.refresh(job)
    return job