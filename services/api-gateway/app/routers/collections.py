"""
api_gateway.app.routers.collections
====================================

CRUD endpoints for user owned document collections

Every endpoint requires authentication and enforces ownership
"""

from __future__ import annotations
import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session


from aletheia_core.db.base import get_db
from aletheia_core.db.models import Collection, User
from aletheia_core.exceptions import ConflictError, NotFoundError
from aletheia_core.schemas.collections import (
    CollectionCreate,
    CollectionList,
    CollectionRead,
    CollectionUpdate,
)
from app.dependencies import get_current_user

router = APIRouter(prefix="/collections", tags=["collections"])

def _get_owned_collections(
        collection_id: uuid.UUID,
        current_user: User,
        db: Session,
) -> Collection:
    """
    Fetch a collection by ID and verify the requesting user owns it
    Raises 404 for doesnt exist and not yours
    """
    collection = db.get(Collection, collection_id)
    if not collection or collection.user_id != current_user.id:
        raise NotFoundError(
            message=f"Collection {collection_id} not found",
            error_code="collection_not_found",
        )
    return collection

@router.post("", response_model=CollectionRead, status_code=status.HTTP_201_CREATED)
def create_collection(
    payload: CollectionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Collection:
    """
    Create a new collection 
    REtuns 409 if the user already has a collection with the same
    name
    """
    existing= db.query(Collection).filter(
        Collection.user_id == current_user.id,
        Collection.name == payload.name,
    ).first()
    if existing:
        raise ConflictError(
            message=f"You already have a collection named {payload.name}.",
            error_code="collection_name_conflict",
        )

    collection = Collection(
        user_id = current_user.id,
        name = payload.name,
        description = payload.description,
    )
    db.add(collection)
    db.commit()
    db.refresh(collection)
    return collection

@router.get("", response_model=CollectionList)
def list_collection(
    db: Session = Depends(get_db),
    current_user : User = Depends(get_current_user),
    skip: int = 0,
    limit: int = 50,
) -> CollectionList:
    """
    list the authenticated user's collection
    """
    query = db.query(Collection).filter(Collection.user_id == current_user.id)
    total = query.count()
    items = query.order_by(Collection.created_at.desc()).offset(skip).limit(limit).all()
    return CollectionList(items = items, total = total)


@router.get("{collection_id}", response_model=CollectionRead)
def get_collection(
    collection_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User  = Depends(get_current_user),
) -> Collection:
    return _get_owned_collections(collection_id, current_user, db)


@router.patch("/{collection_id}", response_model=CollectionRead)
def update_collection(
    collection_id: uuid.UUID,
    payload: CollectionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Collection:
    """
    Partial update so that the fields explicitly set in the 
    request body are changed.
    """
    collection = _get_owned_collections(collection_id, current_user, db)

    
    if payload.name is not None:
        # Check for name conflict with another collection before applying
        conflict = db.query(Collection).filter(
            Collection.user_id == current_user.id,
            Collection.name == payload.name,
            Collection.id != collection_id,
        ).first()
        if conflict:
            raise ConflictError(
                message=f"You already have a collection named '{payload.name}'.",
                error_code="collection_name_conflict",
            )
        collection.name = payload.name

    if payload.description is not None:
        collection.description = payload.description

    db.commit()
    db.refresh(collection)
    return collection


@router.delete("/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_collection(
    collection_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """
    Delete a collection and everything inside it.
    The cascade="all, delete-orphan" on Collection.documents in
    db/models.py means Postgres handles deleting the documents, chunks,
    etc. automatically — the gateway just deletes the collection row.

    Note: this does NOT clean up Qdrant vectors for the deleted chunks.
    """

    collection = _get_owned_collections(collection_id, current_user, db)
    db.delete(collection)
    db.commit()