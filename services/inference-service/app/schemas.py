"""
inference_service.app.schemas
=============================

Internal request/response contracts for the inference service's
HTTP API. These are NOT in aletheia_core because they are internal
service to service contracts
"""

from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field

class EmbedRequest(BaseModel):
    """Embed one or more texts into vectors"""
    texts: list[str] = Field(min_length=1, max_length=512)
    #model defaults to embedding model but can be replaced manually
    # for one off needs without restarting 
    model: str | None = None

class EmbedResponse(BaseModel):
    """Embed response, one vector per input text"""
    embeddings: list[list[float]]
    model: str
    dim: int

class RerankRequest(BaseModel):
    """
    Score a list of candidate passages against a query using
    cross encoder reranker
    """
    query: str = Field(min_length=1)
    candidates: list[str] = Field(min_length=1, max_length=100)

class RerankResponse(BaseModel):
    scores: list[float]
    model: str

class GenerateRequest(BaseModel):
    """Generate a completion from the configured LLM provider"""
    prompt: str = Field(min_length=1)
    system_prompt : str | None = None
    provider: Literal["ollama", "groq"] | None = None
    max_tokens: int = Field(default=1024, ge=1, le=8192)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)

class GenerateResponse(BaseModel):
    content: str
    provider: str
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    embedder: bool
    reranker: bool
    ollama: bool
    groq: bool
