"""
GET /stores/{store_id}/heatmap — zone heatmap endpoint.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query

from api.database import get_pool
from api.models.heatmap import HeatmapResponse
from api.services.heatmap_service import HeatmapService

router = APIRouter(tags=["heatmap"])


async def _get_service() -> HeatmapService:
    pool = await get_pool()
    return HeatmapService(pool=pool)


@router.get(
    "/stores/{store_id}/heatmap",
    response_model=HeatmapResponse,
    summary="Get zone heatmap",
    description=(
        "Returns per-zone visit counts, average dwell time, and a normalised "
        "heat_score (0–1). Zones with fewer than 20 sessions include "
        "data_confidence='LOW'."
    ),
)
async def get_heatmap(
    store_id: str,
    start: Optional[datetime] = Query(None, description="Window start (ISO 8601)"),
    end: Optional[datetime] = Query(None, description="Window end (ISO 8601)"),
    service: HeatmapService = Depends(_get_service),
) -> HeatmapResponse:
    return await service.get_heatmap(store_id=store_id, start=start, end=end)
