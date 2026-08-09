"""
aletheia_core.schemas.ingestion
==================================

Request/Response shapes for the document ingestion API
"""

from __future__ import annotations
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from aletheia_core.db.models import DocumentStatus


class DocumentIngestRequest(BaseModel):
    """
    Request body for ingestion of a new document
    """

    collection_id: uuid.UUID
    content: str | None = Field(default=None, min_length=1)
    source_url: HttpUrl | None = Field(default=None)
    source_name: str | None = Field(default=None, max_length=500)


class DocumentRead(BaseModel):
    """A single document's metadata"""
    
    id: uuid.UUID
    collection_id: uuid.UUID
    source_name: str | None
    source_url: str | None
    status: DocumentStatus
    error_message: str | None
    created_at: str   # ISO 8601 string — datetime serialized for JSON transport

    model_config = ConfigDict(from_attributes=True)


class IngestResponse(BaseModel):
    """
    Returned immediately when an ingestion request is accepted
    """
    job_id : uuid.UUID
    document_id: uuid.UUID
    status: Literal["accepted"] = "accepted"
