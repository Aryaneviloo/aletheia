"""
api_gateway.app.routers.stream
================================

Flow:
  1. Embed query + retrieve chunks (same as /search)
  2. Build context
  3. Open SSE connection to inference-service /generate/stream
  4. Relay tokens to client as they arrive
  5. Save completed response to Dialogue on stream end
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from aletheia_core.config import get_settings
from aletheia_core.db.base import get_db
from aletheia_core.db.models import Chunk, Dialogue, Message, MessageRole, User
from aletheia_core.exceptions import InferenceError
from aletheia_core.logging import get_logger
from aletheia_core.vector.client import get_vector_store
from app.dependencies import get_current_user
from app.routers.collections import _get_owned_collection
from app.routers.search import _embed_query

router = APIRouter(prefix="/stream", tags=["stream"])
log = get_logger(__name__)


class StreamRequest(BaseModel):
    query: str
    collection_ids: list[uuid.UUID]
    dialogue_id: uuid.UUID | None = None


async def _stream_from_inference(
    prompt: str,
    system_prompt: str,
) -> AsyncIterator[str]:
    """Relay SSE tokens from inference-service to the client."""
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{settings.inference_service_url}/generate/stream",
                json={
                    "prompt": prompt,
                    "system_prompt": system_prompt,
                    "max_tokens": 1024,
                    "temperature": 0.7,
                },
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        yield line + "\n\n"
    except httpx.HTTPError as e:
        raise InferenceError(
            message=f"Stream failed: {e}",
            error_code="stream_failed",
        ) from e


@router.post("")
async def stream_synthesis(
    payload: StreamRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """
    Stream a synthesized answer token by token via SSE.
    Connect with: EventSource or fetch with ReadableStream.
    Each chunk: "data: <token>\n\n"
    Final chunk: "data: [DONE]\n\n"
    """
    # Verify ownership
    for collection_id in payload.collection_ids:
        _get_owned_collection(collection_id, current_user, db)

    # Retrieve context (same as /search)
    query_vector = await _embed_query(payload.query)
    vector_store = get_vector_store()

    raw_results = []
    for collection_id in payload.collection_ids:
        hits = vector_store.search(
            query_vector=query_vector,
            collection_id=collection_id,
            limit=10,
        )
        raw_results.extend(hits)

    context = ""
    if raw_results:
        chunk_ids = [r.chunk_id for r in raw_results[:8]]
        chunks = db.query(Chunk).filter(Chunk.id.in_(chunk_ids)).all()
        chunk_map = {c.id: c for c in chunks}
        context_pieces = [
            f"[{i+1}] {chunk_map[r.chunk_id].content}"
            for i, r in enumerate(raw_results[:8])
            if r.chunk_id in chunk_map
        ]
        context = "\n\n".join(context_pieces)

    prompt = f"""Answer using ONLY the context below.

QUESTION: {payload.query}

CONTEXT:
{context or "No relevant context found."}
"""
    system_prompt = "You are Aletheia, a precise assistant. Answer only from the provided context."
    if payload.dialogue_id:
        dialogue = db.get(Dialogue, payload.dialogue_id)
    else:
        dialogue = Dialogue(user_id=current_user.id)
        db.add(dialogue)
        db.flush()

    db.add(Message(
        dialogue_id=dialogue.id,
        role=MessageRole.USER,
        content=payload.query,
    ))
    db.commit()
    dialogue_id = str(dialogue.id)

    async def event_generator() -> AsyncIterator[str]:
        full_response = []
        async for chunk in _stream_from_inference(prompt, system_prompt):
            # Extract token text from SSE line for accumulation
            if chunk.startswith("data: ") and "[DONE]" not in chunk:
                token = chunk[6:].strip().strip("\n")
                full_response.append(token)
            yield chunk

        # Save completed response to DB after stream ends
        if full_response:
            complete_answer = "".join(full_response)
            with __import__('contextlib').suppress(Exception):
                from aletheia_core.db.base import SessionLocal
                save_db = SessionLocal()
                try:
                    save_db.add(Message(
                        dialogue_id=uuid.UUID(dialogue_id),
                        role=MessageRole.ASSISTANT,
                        content=complete_answer,
                    ))
                    save_db.commit()
                finally:
                    save_db.close()


        yield f"data: {{\"dialogue_id\": \"{dialogue_id}\"}}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering if behind a proxy
        },
    )