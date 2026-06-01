"""Pydantic models for zone heatmap response."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ZoneHeat(BaseModel):
    """Heat data for a single zone."""

    zone_id: str
    visits: int = 0
    avg_dwell_ms: float = 0.0
    heat_score: float = 0.0
    data_confidence: str | None = None  # "LOW" when sessions < 20


class HeatmapResponse(BaseModel):
    """Response for GET /stores/{id}/heatmap."""

    store_id: str
    zones: list[ZoneHeat] = Field(default_factory=list)
