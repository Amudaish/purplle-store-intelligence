"""
Event emitter — serialises pipeline events to the canonical schema and
publishes them via two channels:

1. **Redis Streams** (`store_events`)  — consumed by the API in real time.
2. **JSONL file** (`data/events_output.jsonl`) — offline replay & audit trail.

Event schema
------------
{
    "event_id":   "<uuid4>",
    "store_id":   "store_001",
    "camera_id":  "cam_entry",
    "visitor_id": "<uuid4>",
    "event_type": "ENTRY|EXIT|REENTRY|ZONE_ENTER|ZONE_EXIT|ZONE_DWELL|
                   BILLING_QUEUE_JOIN|BILLING_QUEUE_ABANDON",
    "timestamp":  "2024-01-15T10:32:14.123456+00:00",   # ISO 8601 UTC
    "zone_id":    "cosmetics",        # or null
    "dwell_ms":   12500,              # or null
    "is_staff":   false,
    "confidence": 0.87,
    "metadata":   {}
}
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import requests as _requests  # type: ignore
except ImportError:  # pipeline might not have requests
    _requests = None  # type: ignore

logger = logging.getLogger(__name__)

_STREAM_KEY = "store_events"
_DEFAULT_OUTPUT = Path("data") / "events_output.jsonl"


class EventEmitter:
    """
    Serialises and publishes structured store events.

    Parameters
    ----------
    redis_client  : redis.Redis instance (or None to skip Redis publishing).
    store_id      : Store identifier, e.g. 'store_001'.
    camera_id     : Camera identifier, e.g. 'cam_entry'.
    video_start_ts: Wall-clock datetime for frame 0 of the video. Used to
                    convert frame indices to ISO timestamps.
    frame_rate    : Video frame rate (default 15 FPS).
    output_path   : Path to the JSONL file for offline output.
    api_url       : Optional URL to POST events to the REST API directly.
    """

    def __init__(
        self,
        redis_client,
        store_id: str,
        camera_id: str,
        video_start_ts: datetime,
        frame_rate: int = 15,
        output_path: Path = _DEFAULT_OUTPUT,
        api_url: Optional[str] = None,
    ) -> None:
        self.redis = redis_client
        self.store_id = store_id
        self.camera_id = camera_id
        self.video_start_ts = video_start_ts.replace(tzinfo=timezone.utc) \
            if video_start_ts.tzinfo is None else video_start_ts
        self.frame_rate = frame_rate
        self.output_path = output_path
        self.api_url = api_url
        self._buffer: List[Dict[str, Any]] = []
        self._total_emitted = 0

        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self._jsonl_file = open(output_path, "a", encoding="utf-8")  # noqa: WPS515

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def emit_entry(
        self, visitor_id: str, frame_idx: int, confidence: float, is_staff: bool
    ) -> None:
        self._emit(
            event_type="ENTRY",
            visitor_id=visitor_id,
            frame_idx=frame_idx,
            confidence=confidence,
            is_staff=is_staff,
        )

    def emit_exit(
        self, visitor_id: str, frame_idx: int, confidence: float, is_staff: bool,
        dwell_ms: int,
    ) -> None:
        self._emit(
            event_type="EXIT",
            visitor_id=visitor_id,
            frame_idx=frame_idx,
            confidence=confidence,
            is_staff=is_staff,
            dwell_ms=dwell_ms,
        )

    def emit_reentry(
        self, visitor_id: str, frame_idx: int, confidence: float, is_staff: bool
    ) -> None:
        self._emit(
            event_type="REENTRY",
            visitor_id=visitor_id,
            frame_idx=frame_idx,
            confidence=confidence,
            is_staff=is_staff,
        )

    def emit_zone_enter(
        self, visitor_id: str, zone_id: str, frame_idx: int,
        confidence: float, is_staff: bool,
    ) -> None:
        self._emit(
            event_type="ZONE_ENTER",
            visitor_id=visitor_id,
            frame_idx=frame_idx,
            confidence=confidence,
            is_staff=is_staff,
            zone_id=zone_id,
        )

    def emit_zone_exit(
        self, visitor_id: str, zone_id: str, dwell_ms: int,
        frame_idx: int, confidence: float, is_staff: bool,
    ) -> None:
        self._emit(
            event_type="ZONE_EXIT",
            visitor_id=visitor_id,
            frame_idx=frame_idx,
            confidence=confidence,
            is_staff=is_staff,
            zone_id=zone_id,
            dwell_ms=dwell_ms,
        )

    def emit_zone_dwell(
        self, visitor_id: str, zone_id: str, dwell_ms: int,
        frame_idx: int, confidence: float, is_staff: bool,
    ) -> None:
        self._emit(
            event_type="ZONE_DWELL",
            visitor_id=visitor_id,
            frame_idx=frame_idx,
            confidence=confidence,
            is_staff=is_staff,
            zone_id=zone_id,
            dwell_ms=dwell_ms,
        )

    def emit_billing_queue_join(
        self, visitor_id: str, frame_idx: int, confidence: float,
        is_staff: bool, queue_depth: int,
    ) -> None:
        self._emit(
            event_type="BILLING_QUEUE_JOIN",
            visitor_id=visitor_id,
            frame_idx=frame_idx,
            confidence=confidence,
            is_staff=is_staff,
            zone_id="billing",
            metadata={"queue_depth": queue_depth},
        )

    def emit_billing_queue_abandon(
        self, visitor_id: str, frame_idx: int, confidence: float,
        is_staff: bool, dwell_ms: int,
    ) -> None:
        self._emit(
            event_type="BILLING_QUEUE_ABANDON",
            visitor_id=visitor_id,
            frame_idx=frame_idx,
            confidence=confidence,
            is_staff=is_staff,
            zone_id="billing",
            dwell_ms=dwell_ms,
        )

    def flush(self) -> int:
        """
        Flush buffered events: publish to Redis Streams, write JSONL, and
        optionally POST to API.  Returns number of events flushed.
        """
        if not self._buffer:
            return 0

        count = 0
        batch = list(self._buffer)
        for event in batch:
            self._publish_redis(event)
            self._write_jsonl(event)
            count += 1

        # POST batch to API for PostgreSQL persistence
        if self.api_url and batch:
            self._post_api(batch)

        self._buffer.clear()
        self._total_emitted += count
        return count

    def close(self) -> None:
        """Flush remaining events and close the JSONL file."""
        self.flush()
        try:
            self._jsonl_file.close()
        except OSError:
            pass
        logger.info(
            "EventEmitter closed. Total events emitted: %d", self._total_emitted
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _frame_to_timestamp(self, frame_idx: int) -> datetime:
        """Convert frame index to wall-clock UTC timestamp."""
        from datetime import timedelta
        offset_s = frame_idx / self.frame_rate
        return self.video_start_ts + timedelta(seconds=offset_s)

    def _emit(
        self,
        event_type: str,
        visitor_id: str,
        frame_idx: int,
        confidence: float,
        is_staff: bool,
        zone_id: Optional[str] = None,
        dwell_ms: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Build an event dict and add it to the buffer."""
        event: Dict[str, Any] = {
            "event_id": str(uuid.uuid4()),
            "store_id": self.store_id,
            "camera_id": self.camera_id,
            "visitor_id": visitor_id,
            "event_type": event_type,
            "timestamp": self._frame_to_timestamp(frame_idx).isoformat(),
            "zone_id": zone_id,
            "dwell_ms": dwell_ms,
            "is_staff": is_staff,
            "confidence": round(confidence, 4),
            "metadata": metadata or {},
        }
        self._buffer.append(event)

        # Auto-flush every 50 events to avoid memory growth
        if len(self._buffer) >= 50:
            self.flush()

    def _publish_redis(self, event: Dict[str, Any]) -> None:
        """Publish event to Redis Stream."""
        if self.redis is None:
            return
        try:
            # Redis XADD — values must be strings
            fields = {k: json.dumps(v) if not isinstance(v, str) else v
                      for k, v in event.items()}
            self.redis.xadd(_STREAM_KEY, fields, maxlen=10_000, approximate=True)
        except Exception as exc:
            logger.warning("Redis XADD failed: %s", exc)

    def _write_jsonl(self, event: Dict[str, Any]) -> None:
        """Append event as a JSON line to the output file."""
        try:
            self._jsonl_file.write(json.dumps(event, default=str) + "\n")
            self._jsonl_file.flush()
        except OSError as exc:
            logger.warning("JSONL write failed: %s", exc)

    def _post_api(self, events: List[Dict[str, Any]]) -> None:
        """POST a batch of events to the /events/ingest endpoint."""
        if _requests is None:
            logger.debug("'requests' not installed — skipping API POST")
            return
        url = f"{self.api_url.rstrip('/')}/events/ingest"
        try:
            resp = _requests.post(url, json={"events": events}, timeout=10)
            if resp.status_code not in (200, 207):
                logger.warning(
                    "API ingest returned %d: %s", resp.status_code, resp.text[:200]
                )
            else:
                result = resp.json()
                if result.get("rejected", 0) > 0:
                    logger.warning(
                        "API ingest: %d/%d events rejected",
                        result["rejected"], result["total"],
                    )
        except Exception as exc:
            logger.warning("API POST failed (events not persisted to DB): %s", exc)
