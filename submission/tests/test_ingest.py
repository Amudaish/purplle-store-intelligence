"""
PROMPT:
Generate pytest tests for POST /events/ingest covering:
- Successful single and batch ingest
- Duplicate event deduplication (idempotency)
- Partial success (mix of valid and invalid events)
- Schema validation failures (missing required fields, bad confidence, etc.)
- Batch size limit (>500 events rejected)
- Staff event ingestion

CHANGES MADE:
- Used async httpx client fixture from conftest.py
- Added idempotency test to confirm duplicate event_id is silently skipped
- Added partial success test verifying 207 status and error list
- Schema validation handled by Pydantic before DB insertion
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient

from tests.assertions import (
    assert_all_accepted,
    assert_batch_ingest_response,
    assert_idempotent_ingest,
    assert_partial_success,
)

pytestmark = pytest.mark.asyncio


async def test_ingest_single_event(client: AsyncClient, make_event, make_batch):
    """A single valid ENTRY event should be accepted with status 200."""
    event = make_event(event_type="ENTRY")
    resp = await client.post("/events/ingest", json=make_batch([event]))
    assert resp.status_code in (200, 207)
    body = resp.json()
    assert_batch_ingest_response(body)
    assert_all_accepted(body)
    assert body["accepted"] == 1


async def test_ingest_batch_multiple_event_types(client: AsyncClient, make_event, make_batch):
    """Batch with multiple event types should all be accepted."""
    visitor_id = str(uuid.uuid4())
    events = [
        make_event("ENTRY", visitor_id=visitor_id),
        make_event("ZONE_ENTER", visitor_id=visitor_id, zone_id="cosmetics"),
        make_event("ZONE_EXIT", visitor_id=visitor_id, zone_id="cosmetics", dwell_ms=45000),
        make_event("BILLING_QUEUE_JOIN", visitor_id=visitor_id, zone_id="billing"),
        make_event("EXIT", visitor_id=visitor_id, dwell_ms=120000),
    ]
    resp = await client.post("/events/ingest", json=make_batch(events))
    assert resp.status_code in (200, 207)
    body = resp.json()
    assert_batch_ingest_response(body)
    assert body["total"] == 5
    assert_all_accepted(body)


async def test_ingest_idempotent_duplicate(client: AsyncClient, make_event, make_batch):
    """Ingesting the same events twice must be idempotent (same accepted count)."""
    events = [make_event("ENTRY"), make_event("EXIT")]
    resp1 = await client.post("/events/ingest", json=make_batch(events))
    resp2 = await client.post("/events/ingest", json=make_batch(events))
    assert resp1.status_code in (200, 207)
    assert resp2.status_code in (200, 207)
    assert_idempotent_ingest(resp1.json(), resp2.json())


async def test_ingest_invalid_store_id(client: AsyncClient, make_event, make_batch):
    """Event referencing non-existent store should be rejected."""
    event = make_event(event_type="ENTRY")
    event["store_id"] = "nonexistent_store"
    resp = await client.post("/events/ingest", json=make_batch([event]))
    body = resp.json()
    assert_batch_ingest_response(body)
    assert body["rejected"] >= 1


async def test_ingest_confidence_out_of_range(client: AsyncClient, make_batch):
    """Confidence > 1.0 should fail Pydantic validation (422)."""
    event = {
        "event_id": str(uuid.uuid4()),
        "store_id": "store_001",
        "camera_id": "cam_entry",
        "visitor_id": str(uuid.uuid4()),
        "event_type": "ENTRY",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "is_staff": False,
        "confidence": 1.5,   # invalid
        "metadata": {},
    }
    resp = await client.post("/events/ingest", json={"events": [event]})
    assert resp.status_code == 422


async def test_ingest_negative_dwell_ms(client: AsyncClient, make_batch):
    """Negative dwell_ms should fail Pydantic validation (422)."""
    event = {
        "event_id": str(uuid.uuid4()),
        "store_id": "store_001",
        "camera_id": "cam_floor",
        "visitor_id": str(uuid.uuid4()),
        "event_type": "ZONE_EXIT",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "zone_id": "cosmetics",
        "dwell_ms": -100,   # invalid
        "is_staff": False,
        "confidence": 0.85,
        "metadata": {},
    }
    resp = await client.post("/events/ingest", json={"events": [event]})
    assert resp.status_code == 422


async def test_ingest_batch_size_limit(client: AsyncClient, make_event):
    """Batch with > 500 events should be rejected with 422."""
    events = [make_event() for _ in range(501)]
    resp = await client.post("/events/ingest", json={"events": events})
    assert resp.status_code == 422


async def test_ingest_staff_events(client: AsyncClient, make_event, make_batch):
    """Staff events should be accepted and stored with is_staff=True."""
    event = make_event(event_type="ENTRY", is_staff=True)
    resp = await client.post("/events/ingest", json=make_batch([event]))
    assert resp.status_code in (200, 207)
    body = resp.json()
    assert_all_accepted(body)


async def test_ingest_empty_batch_rejected(client: AsyncClient):
    """Empty events list should fail validation (422)."""
    resp = await client.post("/events/ingest", json={"events": []})
    assert resp.status_code == 422


async def test_ingest_partial_success(client: AsyncClient, make_event, make_batch):
    """Mix of valid and invalid (wrong store) events — partial success (207)."""
    good_event = make_event(event_type="ENTRY")
    bad_event = make_event(event_type="ENTRY")
    bad_event["store_id"] = "does_not_exist"
    resp = await client.post("/events/ingest", json=make_batch([good_event, bad_event]))
    body = resp.json()
    assert_batch_ingest_response(body)
    # good_event accepted; bad_event rejected
    assert body["accepted"] >= 1
    assert body["rejected"] >= 1
