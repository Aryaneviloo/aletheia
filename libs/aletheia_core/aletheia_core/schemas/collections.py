"""
aletheia_core.schemas.collections
==================================

Request/response shapes for the collections API

A collection is a named, per user grouping of documents
"""

from __future__ import annotations
import datetime
import uuid

from pydantic import BaseModel, ConfigDict, Field


class CollectionCreate(BaseModel):
    """Request body for creating new collection"""
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)


class CollectionUpdate(BaseModel):
    """Request body for updating an exisitng collection"""
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)


class CollectionRead(BaseModel):
    """A single collection, safe to return in an API response"""

    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)


class CollectionList(BaseModel):
    """
    Paginated list of collections
    Wrapping the list in an object is deliberate
    """

    items: list[CollectionRead]
    total: int 