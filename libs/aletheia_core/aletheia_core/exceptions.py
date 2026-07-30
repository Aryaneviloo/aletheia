"""
aletheia_core.exception
==========================

Shared exception heirarchy for every Aletheia service
Every service should catch library-specific errors as close to the
source as possible and re-raise one of these instead

Usage
-----
    from aletheia_core.exceptions import NotFoundError

    document = db.get(Document, document_id)
    if document is None:
        raise NotFoundError(
            message=f"Document {document_id} was not found.",
            error_code="document_not_found",
        )
"""

from __future__ import annotations

class AletheiaError(Exception):
    """
    Base class for evevry intentional expected error in the system.
    """
    def __init__(self, message: str, error_code: str) -> None:
        self.message = message
        self.error_code = error_code
        super().__init__(message)

    def __repr__(self) -> str:
    
        return f"{self.__class__.__name__}(error_code={self.error_code!r}, message={self.message!r})"


class NotFoundError(AletheiaError):
    """
    Requested resource doesn't exist. Maps to HTTP 404.
    Ex: a document_id or job_id
    """

class ValidationError(AletheiaError):
    """
    Input was well-formed but semantically invalid in a way Pydantic's
    schema validation alone can't catch. Maps to HTTP 422.
    Ex: chunk size larger than the embedding model
    """

class AuthenticationError(AletheiaError):
    """
    Credentials are missing, malformed or invalid. Maps to HTTP 401
    Ex: a bad password
    """

class AuthorizationError(AletheiaError):
    """
    Caller is authenticated but not permitted to perform this action
    Maps to HTTP 403
    Ex: trying to read another user's private collection
    """

class ConcflictError(AletheiaError):
    """
    Reqeust conflicts with existing ones. Maps to HTTP 409
    Ex: registering with an email that is already taken
    """

class InferenceError(AletheiaError):
    """
    The inference-service failed. Maps to HTTP 502
    Ex: Ollama unreachable
    """

class VectorStoreError(AletheiaError):
    """
    Qdrant operation failed. Maps to 502
    Ex: search request errored
    """

class TaskTimeoutError(AletheiaError):
    """
    A celery task didn't complete within its allowed time budget
    Maps to HTTP 504
    """

    