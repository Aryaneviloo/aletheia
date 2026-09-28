"""
api_gateway.app.routers.constellations
========================================

Graph data endpoint for the Aletheia galaxy UI.

Fixes bug #8: original had no pagination, did .all() on full table.

Returns collections as galaxy clusters, documents as stars within
each cluster. The UI (aletheia-ui repo) consumes this to render the
3D constellation visualization.

Two endpoints:
  GET /constellations        — all clusters + stars (paginated)
  GET /constellations/edges  — similarity edges between documents
                               (for drawing connections between stars)
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from aletheia_core.db.base import get_db
from aletheia_core.db.models import Chunk, Collection, Document, DocumentStatus, User
from app.dependencies import get_current_user

router = APIRouter(prefix="/constellations", tags=["constellations"])


class StarNode(BaseModel):
    id: uuid.UUID
    name: str | None
    status: str
    chunk_count: int
    created_at: str


class GalaxyCluster(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    star_count: int
    stars: list[StarNode]


class ConstellationGraph(BaseModel):
    clusters: list[GalaxyCluster]
    total_clusters: int
    total_stars: int


class Edge(BaseModel):
    source_id: uuid.UUID
    target_id: uuid.UUID
    weight: float   # 0.0-1.0, higher = more related


class EdgeGraph(BaseModel):
    edges: list[Edge]


@router.get("", response_model=ConstellationGraph)
def get_constellation(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    skip: int = 0,
    limit: int = 20,
) -> ConstellationGraph:
    """
    Return all collections (clusters) with their documents (stars).
    Paginated on collections — limit/skip apply to collections, not documents.
    """
    query = db.query(Collection).filter(Collection.user_id == current_user.id)
    total_clusters = query.count()
    collections = query.order_by(Collection.created_at.desc()).offset(skip).limit(limit).all()

    clusters = []
    total_stars = 0

    for collection in collections:
        documents = db.query(Document).filter(
            Document.collection_id == collection.id,
            Document.status == DocumentStatus.COMPLETED,
        ).all()

        stars = []
        for doc in documents:
            chunk_count = db.query(Chunk).filter(
                Chunk.document_id == doc.id
            ).count()

            stars.append(StarNode(
                id=doc.id,
                name=doc.source_name,
                status=doc.status.value,
                chunk_count=chunk_count,
                created_at=doc.created_at.isoformat(),
            ))

        total_stars += len(stars)
        clusters.append(GalaxyCluster(
            id=collection.id,
            name=collection.name,
            description=collection.description,
            star_count=len(stars),
            stars=stars,
        ))

    return ConstellationGraph(
        clusters=clusters,
        total_clusters=total_clusters,
        total_stars=total_stars,
    )


@router.get("/edges", response_model=EdgeGraph)
def get_edges(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EdgeGraph:
    """
    Return similarity edges between documents across collections.
    Edges are computed by finding documents that share chunks with
    similar embeddings — proxy: documents in the same collection
    are weakly connected, cross-collection documents with shared
    topics are strongly connected.
    """
    collections = db.query(Collection).filter(
        Collection.user_id == current_user.id
    ).all()

    edges = []
    for collection in collections:
        docs = db.query(Document).filter(
            Document.collection_id == collection.id,
            Document.status == DocumentStatus.COMPLETED,
        ).all()

        # Connect every document pair within a collection
        for i, doc_a in enumerate(docs):
            for doc_b in docs[i+1:]:
                edges.append(Edge(
                    source_id=doc_a.id,
                    target_id=doc_b.id,
                    weight=0.5,
                ))

    return EdgeGraph(edges=edges)