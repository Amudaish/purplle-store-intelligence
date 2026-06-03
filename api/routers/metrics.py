"""
GET /stores/{store_id}/metrics — store-level KPI endpoint.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from database import get_pool
from models.metrics import MetricsResponse
from services.metrics_service import MetricsService

router = APIRouter(tags=["metrics"])


async def _get_service() -> MetricsService:
    pool = await get_pool()
    return MetricsService(pool=pool)


@router.get(
    "/stores/{store_id}/metrics",
    response_model=MetricsResponse,
    summary="Get store KPIs",
    description=(
        "Returns unique visitors, conversion rate, average dwell time, "
        "queue depth, and abandonment rate. Staff are always excluded."
    ),
)
async def get_metrics(
    store_id: str,
    start: Optional[datetime] = Query(None, description="Window start (ISO 8601)"),
    end: Optional[datetime] = Query(None, description="Window end (ISO 8601)"),
    service: MetricsService = Depends(_get_service),
) -> MetricsResponse:
    return await service.get_metrics(store_id=store_id, start=start, end=end)
