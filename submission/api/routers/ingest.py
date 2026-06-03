"""
POST /events/ingest — batch event ingestion endpoint.

Accepts up to 500 events per request.
Returns a partial-success response with per-event errors.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse

from api.database import get_pool
from api.models.events import BatchIngestRequest, BatchIngestResponse
from api.services.ingestion import IngestionService

router = APIRouter(tags=["events"])


async def _get_service(request: Request) -> IngestionService:
    pool = await get_pool()
    redis = getattr(request.app.state, "redis", None)
    return IngestionService(pool=pool, redis=redis)


@router.post(
    "/events/ingest",
    response_model=BatchIngestResponse,
    status_code=status.HTTP_207_MULTI_STATUS,
    summary="Batch ingest store events",
    description=(
        "Ingest up to 500 events in a single request. "
        "Duplicate events (same event_id) are silently de-duplicated. "
        "Returns a 207 with per-event success/failure detail."
    ),
)
async def ingest_events(
    payload: BatchIngestRequest,
    request: Request,
    service: IngestionService = Depends(_get_service),
) -> BatchIngestResponse:
    # Expose event count to logging middleware via request state
    request.state.event_count = len(payload.events)

    trace_id = getattr(request.state, "trace_id", None)
    result = await service.ingest_batch(
        events=payload.events,
        request_trace_id=trace_id,
    )

    # Return 207 if there are partial errors, 200 if all accepted
    status_code = (
        status.HTTP_207_MULTI_STATUS
        if result.errors
        else status.HTTP_200_OK
    )
    return JSONResponse(
        content=result.model_dump(mode="json"),
        status_code=status_code,
    )
