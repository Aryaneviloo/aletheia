"""
aletheia_core.vector.client
===============================

Thin wrapper around qdrant the place where embedding vector is
written or read. Postgres stores everything about a chunk except
the vector itself

Multi-tenancy design
----------------------
One physical qdrant collection holds chunks from every user and
every Aletheia Collection instead of qdrant per user

Usage
-----
    from aletheia_core.vector.client import get_vector_store, ChunkPoint

    store = get_vector_store()
    store.ensure_collection()  # once, at service startup
    store.upsert_chunks([
        ChunkPoint(point_id=chunk.qdrant_point_id, vector=embedding,
                   chunk_id=chunk.id, document_id=chunk.document_id,
                   collection_id=chunk.collection_id)
    ])
    results = store.search(query_vector=query_embedding, collection_id=collection.id, limit=10)
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from functools import lru_cache

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from aletheia_core.config import get_settings
from aletheia_core.exceptions import VectorStoreError
from aletheia_core.logging import get_logger

log = get_logger(__name__)


@dataclass
class ChunkPoint:
    """
    One chunk's vector plus the payload metadata Qdrant needs to filter
    on. A plain dataclass, we don't need Pydantic's validation overhead
    """

    point_id: uuid.UUID
    vector: list[float]
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    collection_id: uuid.UUID


@dataclass
class SearchResult:
    """One scored match returned from a similarity search."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    score: float 


class VectorStore:
    """
    Wraps a QdrantClient bound to one collection.
    """

    def __init__(self, client: QdrantClient, collection_name: str, vector_size: int) -> None:
        self._client = client
        self._collection_name = collection_name
        self._vector_size = vector_size

    def ensure_collection(self) -> None:
        """
        Create the collection if it doesn't exist yet. 
        """
        try:
            if self._client.collection_exists(self._collection_name):
                log.info("qdrant_collection_exists", collection=self._collection_name)
                return

            self._client.create_collection(
                collection_name=self._collection_name,
                vectors_config=qmodels.VectorParams(
                    size=self._vector_size,
                    distance=qmodels.Distance.COSINE,
                ),
            )
            self._client.create_payload_index(
                collection_name=self._collection_name,
                field_name="collection_id",
                field_schema=qmodels.PayloadSchemaType.KEYWORD,
            )
            log.info("qdrant_collection_created", collection=self._collection_name, vector_size=self._vector_size)
        except Exception as e:
            raise VectorStoreError(
                message=f"Failed to provision Qdrant collection '{self._collection_name}'.",
                error_code="qdrant_provision_failed",
            ) from e

    def upsert_chunks(self, points: list[ChunkPoint]) -> None:
        """
        Write (or overwrite, if point_id already exists — that's what
        "upsert" means: UPDATE-if-present, INSERT-if-not) a batch of
        chunk vectors
        """
        if not points:
            return
        try:
            self._client.upsert(
                collection_name=self._collection_name,
                points=[
                    qmodels.PointStruct(
                        id=str(p.point_id),
                        vector=p.vector,
                        payload={
                            "chunk_id": str(p.chunk_id),
                            "document_id": str(p.document_id),
                            "collection_id": str(p.collection_id),
                        },
                    )
                    for p in points
                ],
            )
            log.info("qdrant_upsert", count=len(points), collection=self._collection_name)
        except Exception as e:
            raise VectorStoreError(
                message=f"Failed to upsert {len(points)} chunk(s) into Qdrant.",
                error_code="qdrant_upsert_failed",
            ) from e

    def search(
        self,
        query_vector: list[float],
        collection_id: uuid.UUID,
        limit: int = 10,
        score_threshold: float | None = None,
    ) -> list[SearchResult]:
        """
        Find the `limit` chunks most similar to query_vector, filtered
        to only this collection_id.
        """
        try:
            response = self._client.query_points(
                collection_name=self._collection_name,
                query=query_vector,
                query_filter=qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(
                            key="collection_id",
                            match=qmodels.MatchValue(value=str(collection_id)),
                        )
                    ]
                ),
                limit=limit,
                score_threshold=score_threshold,
            )
            return [
                SearchResult(
                    chunk_id=uuid.UUID(point.payload["chunk_id"]),
                    document_id=uuid.UUID(point.payload["document_id"]),
                    score=point.score,
                )
                for point in response.points
            ]
        except Exception as e:
            raise VectorStoreError(
                message="Qdrant search failed.",
                error_code="qdrant_search_failed",
            ) from e

    def delete_by_document(self, document_id: uuid.UUID) -> None:
        """
        Delete every point belonging to one document
        """
        try:
            self._client.delete(
                collection_name=self._collection_name,
                points_selector=qmodels.FilterSelector(
                    filter=qmodels.Filter(
                        must=[
                            qmodels.FieldCondition(
                                key="document_id",
                                match=qmodels.MatchValue(value=str(document_id)),
                            )
                        ]
                    )
                ),
            )
            log.info("qdrant_delete_by_document", document_id=str(document_id))
        except Exception as e:
            raise VectorStoreError(
                message=f"Failed to delete vectors for document {document_id}.",
                error_code="qdrant_delete_failed",
            ) from e


@lru_cache
def get_vector_store() -> VectorStore:
    """
    Building the QdrantClient here reuses one underlying HTTP
    connection pool instead of opening a fresh connection per request.
    """
    settings = get_settings()
    client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)
    collection_name = f"{settings.qdrant_collection_prefix}_chunks"
    return VectorStore(client=client, collection_name=collection_name, vector_size=settings.embedding_dim)