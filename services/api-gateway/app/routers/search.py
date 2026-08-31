"""
api_gateway.app.routers.search
================================

Pipeline per request:
  1. Validate collection ownership for every collection_id in the request
  2. POST /embed to inference-service → get query vector
  3. Search Qdrant for each collection, merge results
  4. POST /rerank to inference-service → score candidates
  5. Sort by rerank score, return top `limit` results

This is synchronous (not a Celery task) because search is a fast
read operation the client expects a direct response from, unlike
ingestion which may take tens of seconds.
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from aletheia_core.config import get_settings
from aletheia_core.db.base import get_db
from aletheia_core.db.models import Chunk, User
from aletheia_core.exceptions import InferenceError, NotFoundError
from aletheia_core.schemas.search import ChunkResult, SearchRequest, SearchResponse
from aletheia_core.vector.client import get_vector_store
from app.dependencies import get_current_user
from app.routers.collections import _get_owned_collection

router = APIRouter(prefix="/search", tags=["search"])


async def _embed_query(query: str) -> list[float]:
    """
    Call inference-service /embed to get the query vector.
    Uses a fresh httpx client per call 
    """
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{settings.inference_service_url}/embed",
                json={"texts": [query]},
            )
            response.raise_for_status()
            data = response.json()
            return data["embeddings"][0]
    except httpx.HTTPError as e:
        raise InferenceError(
            message=f"Failed to embed query: {e}",
            error_code="embed_query_failed",
        ) from e


async def _rerank_results(
    query: str,
    candidates: list[str],
) -> list[float]:
    """Call inference-service /rerank to score candidates."""
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{settings.inference_service_url}/rerank",
                json={"query": query, "candidates": candidates},
            )
            response.raise_for_status()
            data = response.json()
            return data["scores"]
    except httpx.HTTPError as e:
        raise InferenceError(
            message=f"Failed to rerank results: {e}",
            error_code="rerank_failed",
        ) from e


@router.post("", response_model=SearchResponse)
async def search(
    payload: SearchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SearchResponse:
    """
    Search across one or more collections owned by the current user.
    """
    # Verify ownership of every collection in
    for collection_id in payload.collection_ids:
        _get_owned_collection(collection_id, current_user, db)

    # Step 1: embed the query
    query_vector = await _embed_query(payload.query)

    # Step 2: search each collection in Qdrant
    vector_store = get_vector_store()
    raw_results = []
    for collection_id in payload.collection_ids:
        hits = vector_store.search(
            query_vector=query_vector,
            collection_id=collection_id,
            limit=payload.limit * 2,   # retrieve more than needed before reranking
            score_threshold=payload.score_threshold,
        )
        raw_results.extend(hits)

    if not raw_results:
        return SearchResponse(
            query=payload.query,
            results=[],
            total_found=0,
        )

    # Step 3: load chunk content from Postgres for reranking
    # Qdrant only stores the vector + payload IDs
    chunk_ids = [r.chunk_id for r in raw_results]
    chunks = db.query(Chunk).filter(Chunk.id.in_(chunk_ids)).all()
    chunk_map = {c.id: c for c in chunks}

    # Step 4: rerank using chunk content
    candidate_texts = [
        chunk_map[r.chunk_id].content
        for r in raw_results
        if r.chunk_id in chunk_map
    ]

    if not candidate_texts:
        return SearchResponse(query=payload.query, results=[], total_found=0)

    rerank_scores = await _rerank_results(payload.query, candidate_texts)

    # Step 5: build results with both retrieval and rerank scores,
    # sort by rerank score descending, return top `limit`
    results = []
    for i, hit in enumerate(raw_results):
        chunk = chunk_map.get(hit.chunk_id)
        if not chunk:
            continue
        results.append(ChunkResult(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            collection_id=chunk.collection_id,
            content=chunk.content,
            retrieval_score=hit.score,
            rerank_score=rerank_scores[i] if i < len(rerank_scores) else None,
        ))

    results.sort(key=lambda r: r.rerank_score or 0, reverse=True)
    results = results[:payload.limit]

    return SearchResponse(
        query=payload.query,
        results=results,
        total_found=len(results),
    )