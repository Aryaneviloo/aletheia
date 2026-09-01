"""
aletheia_core.schemas.jobs
============================

Request/Response shapes for job status polling
"""

from __future__ import annotations
import dataclasses
import uuid
import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from aletheia_core.db.models import JobStatus, JobType


class JobRead(BaseModel):
    """
    Full job record, returned when polling for status
    result is typed as any because its shape varies by the job type
    """
    id: uuid.UUID
    job_type: JobType
    status: JobStatus
    result: Any | None
    error_message: str | None
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)


class JobList(BaseModel):
    """Pagitated list of jobs kinda same as COllectionslist"""
    items: list[JobRead]
    total: int

