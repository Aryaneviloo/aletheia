"""
aletheia_core.schemas.search
============================

Request/Response shapes for vector search and retrieval
Search in ALetheia:
   1. Embed the query -> find nearest chunks in Qdrant
   2. Rerank the candidates with a cross encoder
"""

from __future__ import annotations
import uuid
from pydantic import BaseModel, Field



class SearchRequest(BaseModel):
    """Request body for a retreival search"""
    query: str = Field(min_length=1, max_length=2000)
    collections_ids: list[uuid.UUID] = Field(
        min_length=1,
        description="Search within these specific collections only"
                    "Must belong to the authenticated user - the router"
                    "Validates ownership before dispatching"
    )
    limit: int = Field(default=10, ge=1, le=50)
    score_threshold: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Drop any result below this similarity score"
                    "None menas return top-limit results regardless of score"
    
    )

class ChunkResult(BaseModel):
    """
    One retrieved chunk, with its retrieval and reranking score"""
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    collection_id: uuid.UUID
    content: str
    retrieval_score: float
    rerank_score: float | None = None


class SearchResponse(BaseModel):
    """Ranked list of chunks matching the query."""

    query: str
    results: list[ChunkResult]
    total_found: int