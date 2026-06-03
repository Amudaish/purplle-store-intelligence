"""
GET /stores/{store_id}/funnel — session-based conversion funnel endpoint.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query

from database import get_pool
from models.funnel import FunnelResponse
from services.funnel_service import FunnelService

router = APIRouter(tags=["funnel"])


async def _get_service() -> FunnelService:
    pool = await get_pool()
    return FunnelService(pool=pool)


@router.get(
    "/stores/{store_id}/funnel",
    response_model=FunnelResponse,
    summary="Get conversion funnel",
    description=(
        "Returns the visitor conversion funnel: "
        "Entry → Zone Visit → Billing Queue → Purchase, "
        "with drop-off percentages and re-entry session count."
    ),
)
async def get_funnel(
    store_id: str,
    start: Optional[datetime] = Query(None, description="Window start (ISO 8601)"),
    end: Optional[datetime] = Query(None, description="Window end (ISO 8601)"),
    service: FunnelService = Depends(_get_service),
) -> FunnelResponse:
    return await service.get_funnel(store_id=store_id, start=start, end=end)
