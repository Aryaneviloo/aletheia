"""
api_gateway.app.main
====================

FastAPI application factory for the Aletheia API gateway

The gateway ensures:
 - Accept and validate HTTP requests
 - Authenticate callers via JWT
 - Dispatch async work to Celery workers
 - Proxy real time inference calls to inference service
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from aletheia_core.config import get_settings
from aletheia_core.exceptions import (
    AletheiaError,
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    InferenceError,
    NotFoundError,
    TaskTimeoutError,
    ValidationError,
    VectorStoreError,
)
from aletheia_core.logging import configure_logging, get_logger
from app.middleware.request_id import RequestIDMiddleware
from app.routers import auth, health


log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings)

    log.info(
        "api_gateway_starting",
        environment=settings.environment,
    )

    yield

    log.info("api_gateway_shutting_down")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Aletheia API Gateway",
        version="0.1.0",
        description=(
            "Offline RAG orchestration — ingest, retrieve, synthesize, judge."
        ),
        lifespan=lifespan,
        # Disable the default /docs and /redoc in production.
        # They expose your full API schema publicly.
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url="/redoc" if settings.environment != "production" else None,
    )

    # --- Middleware -------------------------------------------------------

    # Middleware is applied in reverse order.
    # The last added middleware runs first.
    app.add_middleware(RequestIDMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Exception handlers ----------------------------------------------

    # Maps each AletheiaError subclass to the correct HTTP status code.
    _exc_status_map = {
        NotFoundError: 404,
        ValidationError: 422,
        AuthenticationError: 401,
        AuthorizationError: 403,
        ConflictError: 409,
        InferenceError: 502,
        VectorStoreError: 502,
        TaskTimeoutError: 504,
    }

    def make_handler(sc: int):
        async def handler(request, exc: AletheiaError) -> JSONResponse:
            log.warning(
                "request_error",
                error_code=exc.error_code,
                message=exc.message,
                status_code=sc,
            )

            return JSONResponse(
                status_code=sc,
                content={
                    "error_code": exc.error_code,
                    "message": exc.message,
                },
            )

        return handler

    for exc_class, status_code in _exc_status_map.items():
        app.add_exception_handler(
            exc_class,
            make_handler(status_code),
        )

    # --- Routers ----------------------------------------------------------

    app.include_router(health.router)
    app.include_router(auth.router)

    # Phases 8-11 add:
    # collections, ingestion, search, jobs, synthesis, stream

    return app


app = create_app()