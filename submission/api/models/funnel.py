"""Pydantic models for conversion funnel response."""

from __future__ import annotations

from pydantic import BaseModel, Field


class FunnelStage(BaseModel):
    """Single stage in the conversion funnel."""

    stage: str
    count: int
    pct: float = 0.0
    drop_off: float | None = None


class FunnelResponse(BaseModel):
    """Response for GET /stores/{id}/funnel."""

    store_id: str
    funnel: list[FunnelStage] = Field(default_factory=list)
    reentry_sessions: int = 0
