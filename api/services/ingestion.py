"""
Event ingestion service.

Handles idempotent batch insertion of events into PostgreSQL and publishes
each accepted event to the Redis Stream for real-time consumers.

Key behaviours
--------------
- Deduplication: events already present (by event_id PK) are silently skipped.
- Session upsert: maintains visitor_sessions table with entry/exit times,
  zones visited, and billing/purchase flags.
- Partial success: individual event failures don't roll back other events.
- Redis publish: every accepted event is also XADD'd to `store_events` stream.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import asyncpg

from models.events import BatchIngestResponse, EventError, EventIn

logger = logging.getLogger(__name__)

_STREAM_KEY = "store_events"

# Event types that indicate the visitor reached the billing area
_BILLING_EVENTS = {"BILLING_QUEUE_JOIN", "BILLING_QUEUE_ABANDON"}
# Event types that trigger session creation (entry points)
_ENTRY_EVENTS = {"ENTRY", "REENTRY"}
_EXIT_EVENTS = {"EXIT"}


class IngestionService:
    """
    Orchestrates batch event ingestion into PostgreSQL with deduplication
    and session management.

    Parameters
    ----------
    pool      : asyncpg connection pool.
    redis     : redis.asyncio.Redis instance (optional, may be None).
    """

    def __init__(self, pool: asyncpg.Pool, redis=None) -> None:
        self.pool = pool
        self.redis = redis

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def ingest_batch(
        self, events: List[EventIn], request_trace_id: Optional[str] = None
    ) -> BatchIngestResponse:
        """
        Process a batch of up to 500 events.

        Returns a BatchIngestResponse with counts and per-event errors.
        """
        accepted = 0
        errors: List[EventError] = []

        async with self.pool.acquire() as conn:
            for idx, event in enumerate(events):
                try:
                    inserted = await self._insert_event(conn, event)
                    if inserted:
                        await self._upsert_session(conn, event)
                        await self._publish_redis(event)
                        accepted += 1
                    else:
                        # Duplicate — count as accepted (idempotent)
                        accepted += 1
                        logger.debug("Duplicate event ignored: %s", event.event_id)
                except asyncpg.ForeignKeyViolationError as exc:
                    errors.append(
                        EventError(
                            event_id=str(event.event_id),
                            index=idx,
                            error="FOREIGN_KEY_ERROR",
                            message=f"store_id '{event.store_id}' does not exist",
                        )
                    )
                    logger.warning(
                        "FK violation for event %s: %s", event.event_id, exc
                    )
                except Exception as exc:
                    errors.append(
                        EventError(
                            event_id=str(event.event_id),
                            index=idx,
                            error="INTERNAL_ERROR",
                            message=str(exc),
                        )
                    )
                    logger.error(
                        "Failed to ingest event %s: %s", event.event_id, exc
                    )

        return BatchIngestResponse(
            total=len(events),
            accepted=accepted,
            rejected=len(errors),
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _insert_event(self, conn: asyncpg.Connection, event: EventIn) -> bool:
        """
        Insert event into the events table.

        Returns True if inserted, False if already existed (duplicate).
        """
        sql = """
            INSERT INTO events
                (event_id, store_id, camera_id, visitor_id, event_type,
                 timestamp, zone_id, dwell_ms, is_staff, confidence, metadata)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
            ON CONFLICT (event_id) DO NOTHING
        """
        result = await conn.execute(
            sql,
            event.event_id,
            event.store_id,
            event.camera_id,
            event.visitor_id,
            event.event_type.value,
            event.timestamp,
            event.zone_id,
            event.dwell_ms,
            event.is_staff,
            event.confidence,
            json.dumps(event.metadata),
        )
        # 'INSERT 0 1' means inserted, 'INSERT 0 0' means skipped (conflict)
        return result.endswith("1")

    async def _upsert_session(self, conn: asyncpg.Connection, event: EventIn) -> None:
        """
        Maintain the visitor_sessions table based on event type.

        ENTRY / REENTRY → create/update session with entry_time.
        EXIT            → update exit_time.
        ZONE_ENTER      → add zone_id to zones_visited.
        BILLING_*       → set reached_billing=True.
        """
        event_type = event.event_type.value

        if event_type in _ENTRY_EVENTS:
            sql = """
                INSERT INTO visitor_sessions
                    (store_id, visitor_id, is_staff, entry_time, is_reentry)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (store_id, visitor_id, entry_time) DO NOTHING
            """
            await conn.execute(
                sql,
                event.store_id,
                event.visitor_id,
                event.is_staff,
                event.timestamp,
                event_type == "REENTRY",
            )

        elif event_type in _EXIT_EVENTS:
            sql = """
                UPDATE visitor_sessions
                SET exit_time = $1,
                    total_dwell_ms = EXTRACT(EPOCH FROM ($1 - entry_time)) * 1000
                WHERE store_id = $2
                  AND visitor_id = $3
                  AND exit_time IS NULL
            """
            await conn.execute(sql, event.timestamp, event.store_id, event.visitor_id)

        elif event_type == "ZONE_ENTER" and event.zone_id:
            sql = """
                UPDATE visitor_sessions
                SET zones_visited = array_append(zones_visited, $1)
                WHERE store_id = $2
                  AND visitor_id = $3
                  AND exit_time IS NULL
                  AND NOT ($1 = ANY(zones_visited))
            """
            await conn.execute(
                sql, event.zone_id, event.store_id, event.visitor_id
            )

        elif event_type in _BILLING_EVENTS:
            sql = """
                UPDATE visitor_sessions
                SET reached_billing = TRUE
                WHERE store_id = $1
                  AND visitor_id = $2
                  AND exit_time IS NULL
            """
            await conn.execute(sql, event.store_id, event.visitor_id)

    async def _publish_redis(self, event: EventIn) -> None:
        """Publish event to Redis Stream for real-time consumers."""
        if self.redis is None:
            return
        try:
            fields = {
                "event_id": str(event.event_id),
                "store_id": event.store_id,
                "camera_id": event.camera_id,
                "visitor_id": event.visitor_id,
                "event_type": event.event_type.value,
                "timestamp": event.timestamp.isoformat(),
                "zone_id": event.zone_id or "",
                "is_staff": str(event.is_staff),
                "confidence": str(event.confidence),
            }
            await self.redis.xadd(
                _STREAM_KEY, fields, maxlen=10_000, approximate=True
            )
        except Exception as exc:
            logger.warning("Redis XADD failed: %s", exc)
