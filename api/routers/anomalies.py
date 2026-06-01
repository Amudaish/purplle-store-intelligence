"""
GET /stores/{store_id}/anomalies — anomaly detection endpoint.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query

from api.database import get_pool
from api.models.anomalies import AnomalyResponse
from api.services.anomaly_service import AnomalyService

router = APIRouter(tags=["anomalies"])


async def _get_service() -> AnomalyService:
    pool = await get_pool()
    return AnomalyService(pool=pool)


@router.get(
    "/stores/{store_id}/anomalies",
    response_model=AnomalyResponse,
    summary="Detect store anomalies",
    description=(
        "Detects and returns anomalies: QUEUE_SPIKE, CONVERSION_DROP, and DEAD_ZONE. "
        "Each anomaly includes severity (LOW/MEDIUM/HIGH/CRITICAL) and "
        "a suggested corrective action."
    ),
)
async def get_anomalies(
    store_id: str,
    since: Optional[datetime] = Query(
        None,
        description="Only return anomalies detected after this timestamp (ISO 8601). "
                    "Also used as the reference 'now' for detection.",
    ),
    service: AnomalyService = Depends(_get_service),
) -> AnomalyResponse:
    return await service.get_anomalies(store_id=store_id, since=since)
