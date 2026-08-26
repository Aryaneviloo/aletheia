"""
api_gateway.app.middleware.request_id
======================================

Assigns a unique request_id to every incomung request and binds it
to the structured logging context via aletheia_core.logging

A depends() runs only on routes that declare it and middleware runs
on every request - inlcluding 404s, unmatched routes.

The request_id is:
  1. Read from the inbound X request header if present
  2. Generated as a fresh UUID4 if no header is present
  3. Bound to the structlog context so every log line 
     carries it
  4. Added to the response as X-Request-ID so clients can
     reference it 
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from aletheia_core.logging import bind_request_id, clear_context



class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        inbound_id = request.headers.get("X-Request-ID")
        request_id = bind_request_id(inbound_id)

        try:
            response = await call_next(request)

        finally:
            #Always clear context
            clear_context()

        response.headers["X-Request-ID"] = request_id

        return response
    