"""Pydantic models for store metrics response."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class QueueMetrics(BaseModel):
    """Queue depth statistics."""

    current: int = 0
    avg: float = 0.0
    max: int = 0


class MetricsResponse(BaseModel):
    """Response for GET /stores/{id}/metrics."""

    store_id: str
    period: dict[str, str | None] = {}
    unique_visitors: int = 0
    conversion_rate: float = 0.0
    avg_dwell_time_ms: float = 0.0
    queue_depth: QueueMetrics = QueueMetrics()
    abandonment_rate: float = 0.0
    total_transactions: int = 0
    total_revenue_inr: float = 0.0
