"""
inference_service.app.main
============================

FastAPI application for the inference service, embedding, reranking,
and LLM generation, exposed as internal HTTP endpoints.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from aletheia_core.config import get_settings
from aletheia_core.exceptions import AletheiaError
from aletheia_core.logging import configure_logging, get_logger

from app.embedder import get_embedder
from app.ollama_client import get_llm_provider
from app.reranker import get_reranker
from app.schemas import (
    EmbedRequest,
    EmbedResponse,
    GenerateRequest,
    GenerateResponse,
    HealthResponse,
    RerankRequest,
    RerankResponse,
)

log = get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup: configure logging, then load both the models so the request
    doesnt wait long 
    """
    configure_logging(get_settings())
    log.info("inference_service_starting")

    #calling htese to get @lru_cache working
    get_embedder()
    get_reranker()
    log.info("inference_service_ready")
    yield
    log.info("inference_service_shutting_down")

app = FastAPI(title="Aletheia Inference Service", lifespan = lifespan)


@app.exception_handler(AletheiaError)
async def aletheia_error_handler(request, exc: AletheiaError):
    """
    TO catch every aletheia error subclass raised anywhere in this
    service(Inference, Value etc ) and turns it into JSON response
    """

    from fastapi.responses import JSONResponse

    status_map = {
        "InferenceError" : 502,
        "ValidationError": 422,
    }
    status_code = status_map.get(type(exc).__name__, 500)
    return JSONResponse(
        status_code = status_code,
        content = {"error_code": exc.error_code, "message": exc.message},
    )


@app.get("/health", response_model = HealthResponse)
async def health() -> HealthResponse:
    """
    Liveness/readiness check, reports each dependency's status
    """
    settings = get_settings()

    embedder_ok = True
    reranker_ok = True
    try:
        get_embedder()
    except Exception:
        embedder_ok = False
    try: 
        get_reranker()
    except Exception:
        reranker_ok = False

    ollama_ok = settings.llm_provider == "ollama"
    groq_ok = settings.llm_provider == "groq" and bool(settings.groq_api_key)

    overall = "ok" if (embedder_ok and reranker_ok) else "degraded"

@app.post("/embed", response_model = EmbedResponse)
async def embed(payload: EmbedRequest) -> EmbedResponse:
    embedder = get_embedder()
    vectors = embedder.embed(payload.texts)
    return EmbedResponse(embeddings = vectors, model = embedder.model_name, dim=embedder.dim)

@app.post("/rerank", response_model = RerankResponse)
async def rerank(payload: RerankRequest) -> RerankResponse:
    reranker = get_reranker()
    scores = reranker.score(payload.query, payload.candidates)
    return RerankResponse(scores=scores, model = reranker.model_name)

@app.post("/generate", response_model=GenerateResponse)
async def generate(payload: GenerateRequest) -> GenerateResponse:
    provider = get_llm_provider()
    content, prompt_tokens, completion_tokens = await provider.generate(
        prompt=payload.prompt,
        system_prompt=payload.system_prompt,
        max_tokens=payload.max_tokens,
        temperature=payload.temperature,
    )
    settings = get_settings()
    return GenerateResponse(
        content=content,
        provider=settings.llm_provider,
        model=provider.model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )


@app.post("/generate/stream")
async def generate_stream(payload: GenerateRequest) -> StreamingResponse:
    """
    Streaming generation — used by the gateway's own /stream endpoint
    (Phase 11) to relay tokens to a client in real time via
    Server-Sent Events, rather than waiting for the full response.
    """
    provider = get_llm_provider()

    async def token_generator():
        async for token in provider.stream(
            prompt=payload.prompt,
            system_prompt=payload.system_prompt,
            max_tokens=payload.max_tokens,
            temperature=payload.temperature,
        ):
            yield f"data: {token}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(token_generator(), media_type="text/event-stream")

