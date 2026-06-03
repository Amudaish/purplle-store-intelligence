"""Pydantic models for anomaly detection response."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class Anomaly(BaseModel):
    """Single detected anomaly."""

    anomaly_id: str
    type: str  # QUEUE_SPIKE, CONVERSION_DROP, DEAD_ZONE
    severity: str  # LOW, MEDIUM, HIGH, CRITICAL
    detected_at: datetime
    details: dict[str, Any] = Field(default_factory=dict)
    suggested_action: str


class AnomalyResponse(BaseModel):
    """Response for GET /stores/{id}/anomalies."""

    store_id: str
    anomalies: list[Anomaly] = Field(default_factory=list)
