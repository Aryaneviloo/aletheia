"""
api_gateway.app.routers.jobs
==============================

Job status polling — lets a client track the progress of an async
Celery task (ingestion, synthesis, or judge) using the job_id

Polling pattern:
  POST /ingestion        → returns job_id immediately (202 Accepted)
  GET  /jobs/{job_id}   → poll until status is "completed" or "failed"
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from aletheia_core.db.base import get_db
from aletheia_core.db.models import Job, User
from aletheia_core.exceptions import AuthorizationError, NotFoundError
from aletheia_core.schemas.jobs import JobList, JobRead
from app.dependencies import get_current_user

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobRead)
def get_job(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Job:
    """
    Get the current status and result of a job.

    Returns 404 if the job doesn't exist.
    Returns 403 if the job belongs to a different user — same pattern
    as collections: don't reveal that the job exists at all if the
    caller doesn't own it, but here we use 403 instead of 404 because
    a job_id is ephemeral and there's less risk in being slightly more
    specific than with a permanent resource like a collection.
    """
    job = db.get(Job, job_id)
    if not job:
        raise NotFoundError(
            message=f"Job {job_id} not found.",
            error_code="job_not_found",
        )
    if job.user_id != current_user.id:
        raise AuthorizationError(
            message="You don't have access to this job.",
            error_code="job_access_denied",
        )
    return job


@router.get("", response_model=JobList)
def list_jobs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    skip: int = 0,
    limit: int = 50,
) -> JobList:
    """
    List all jobs belonging to the current user, most recent first.
    Useful for a dashboard showing ingestion/synthesis history.
    """
    query = db.query(Job).filter(Job.user_id == current_user.id)
    total = query.count()
    items = query.order_by(Job.created_at.desc()).offset(skip).limit(limit).all()
    return JobList(items=items, total=total)