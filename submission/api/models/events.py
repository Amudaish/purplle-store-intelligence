"""Pydantic models for event ingestion — request and response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class EventType(str, Enum):
    """Valid event types from the detection pipeline."""

    ENTRY = "ENTRY"
    EXIT = "EXIT"
    REENTRY = "REENTRY"
    ZONE_ENTER = "ZONE_ENTER"
    ZONE_EXIT = "ZONE_EXIT"
    ZONE_DWELL = "ZONE_DWELL"
    BILLING_QUEUE_JOIN = "BILLING_QUEUE_JOIN"
    BILLING_QUEUE_ABANDON = "BILLING_QUEUE_ABANDON"


class EventIn(BaseModel):
    """Single event from the detection pipeline."""

    event_id: uuid.UUID
    store_id: str = Field(..., min_length=1, max_length=32)
    camera_id: str = Field(..., min_length=1, max_length=32)
    visitor_id: str = Field(..., min_length=1, max_length=64)
    event_type: EventType
    timestamp: datetime
    zone_id: str | None = None
    dwell_ms: int | None = None
    is_staff: bool = False
    confidence: float = Field(..., ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("dwell_ms")
    @classmethod
    def validate_dwell(cls, v: int | None, info) -> int | None:
        if v is not None and v < 0:
            raise ValueError("dwell_ms must be non-negative")
        return v


class BatchIngestRequest(BaseModel):
    """Batch event ingestion request — up to 500 events."""

    events: list[EventIn] = Field(..., min_length=1, max_length=500)


class EventError(BaseModel):
    """Error detail for a rejected event."""

    event_id: str | None = None
    index: int | None = None
    error: str
    message: str


class BatchIngestResponse(BaseModel):
    """Response from batch event ingestion with partial success support."""

    total: int
    accepted: int
    rejected: int
    errors: list[EventError] = Field(default_factory=list)
