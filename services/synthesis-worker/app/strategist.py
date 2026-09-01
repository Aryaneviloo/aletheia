"""
synthesis_worker.app.strategist
=================================

Collection routing strategy: decides which collections to search
for a given query before synthesis.
"""

from __future__ import annotations

import uuid

import httpx
from sqlalchemy.orm import Session

from aletheia_core.config import get_settings
from aletheia_core.db.models import Collection
from aletheia_core.logging import get_logger
from aletheia_core.vector.client import SearchResult, get_vector_store

log = get_logger(__name__)


def embed_query(query: str) -> list[float]:
    """Embed the query via inference-service."""
    settings = get_settings()
    response = httpx.post(
        f"{settings.inference_service_url}/embed",
        json={"texts": [query]},
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()["embeddings"][0]


def retrieve_candidates(
    query: str,
    collection_ids: list[uuid.UUID],
    user_id: uuid.UUID,
    db: Session,
    limit: int = 20,
) -> list[SearchResult]:
    """
    Retrieve candidate chunks from the specified collections.

    If collection_ids is empty, searches ALL collections belonging
    to the user
    """
    if not collection_ids:
        # Search all user collections
        user_collections = db.query(Collection).filter(
            Collection.user_id == user_id
        ).all()
        collection_ids = [c.id for c in user_collections]

    if not collection_ids:
        log.warning("no_collections_found", user_id=str(user_id))
        return []

    query_vector = embed_query(query)
    vector_store = get_vector_store()

    all_results = []
    for collection_id in collection_ids:
        results = vector_store.search(
            query_vector=query_vector,
            collection_id=collection_id,
            limit=limit,
        )
        all_results.extend(results)

    # Sort by retrieval score, deduplicate by chunk_id
    seen = set()
    unique_results = []
    for r in sorted(all_results, key=lambda x: x.score, reverse=True):
        if r.chunk_id not in seen:
            seen.add(r.chunk_id)
            unique_results.append(r)

    return unique_results[:limit]