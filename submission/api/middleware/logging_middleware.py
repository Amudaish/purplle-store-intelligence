"""
Structured JSON request/response logging middleware.

Logs every HTTP request with the fields required by the spec:
  trace_id, store_id, endpoint, latency_ms, event_count, status_code

Extracts store_id from the URL path when present (/stores/{id}/...).
Extracts event_count from the JSON body for POST /events/ingest.
"""

from __future__ import annotations

import time
import uuid
from typing import Callable

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = structlog.get_logger(__name__)

_STORE_PATH_PREFIX = "/stores/"


class StructuredLoggingMiddleware(BaseHTTPMiddleware):
    """
    Adds structured JSON logging for every request/response cycle.

    Fields emitted
    --------------
    trace_id    : UUID per request (also injected into response headers).
    store_id    : Extracted from URL path, or None.
    endpoint    : "{METHOD} {path}".
    latency_ms  : Wall-clock duration in milliseconds.
    event_count : Number of events in POST /events/ingest body, else None.
    status_code : HTTP status code.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        trace_id = str(uuid.uuid4())
        start = time.perf_counter()

        # Attach trace_id to request state so routers can access it
        request.state.trace_id = trace_id

        # Extract store_id from path
        store_id = _extract_store_id(request.url.path)

        # We cannot read the body here without consuming it, so event_count
        # is populated by the ingest router via request.state
        request.state.event_count = None

        response: Response = await call_next(request)

        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        event_count = getattr(request.state, "event_count", None)

        log_fields = dict(
            trace_id=trace_id,
            store_id=store_id,
            endpoint=f"{request.method} {request.url.path}",
            latency_ms=latency_ms,
            status_code=response.status_code,
        )
        if event_count is not None:
            log_fields["event_count"] = event_count

        if response.status_code >= 500:
            logger.error("request_complete", **log_fields)
        elif response.status_code >= 400:
            logger.warning("request_complete", **log_fields)
        else:
            logger.info("request_complete", **log_fields)

        # Expose trace_id in response header for client correlation
        response.headers["X-Trace-Id"] = trace_id
        return response


def _extract_store_id(path: str) -> str | None:
    """Parse /stores/{store_id}/... → store_id."""
    if _STORE_PATH_PREFIX in path:
        remainder = path[path.index(_STORE_PATH_PREFIX) + len(_STORE_PATH_PREFIX):]
        parts = remainder.split("/")
        if parts and parts[0]:
            return parts[0]
    return None
