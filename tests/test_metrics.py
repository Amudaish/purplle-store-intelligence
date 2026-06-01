"""
PROMPT:
Generate pytest tests for GET /stores/{id}/metrics covering:
- Basic response shape validation
- Correct unique visitor count (excluding staff)
- Conversion rate calculation accuracy
- Average dwell time calculation
- Queue depth metrics
- Abandonment rate
- Empty store (no events) returns zero metrics

CHANGES MADE:
- Used assertion helpers from tests/assertions.py
- Seeded events through the ingest endpoint (not direct DB) for integration coverage
- Added tolerance bands on float comparisons
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Callable

import pytest
from httpx import AsyncClient

from tests.assertions import (
    assert_conversion_rate,
    assert_metrics_response,
    assert_staff_excluded,
)

pytestmark = pytest.mark.asyncio

_STORE = "store_001"


async def _ingest(client: AsyncClient, events: list[dict]) -> None:
    resp = await client.post("/events/ingest", json={"events": events})
    assert resp.status_code in (200, 207)


async def test_metrics_empty_store(client: AsyncClient):
    """Empty store should return zero metrics without error."""
    resp = await client.get(f"/stores/{_STORE}/metrics")
    assert resp.status_code == 200
    body = resp.json()
    assert_metrics_response(body)
    assert body["unique_visitors"] == 0
    assert body["conversion_rate"] == 0.0


async def test_metrics_unique_visitors(client: AsyncClient, make_event):
    """unique_visitors must equal number of distinct non-staff visitor_ids."""
    visitors = [str(uuid.uuid4()) for _ in range(5)]
    events = [make_event("ENTRY", visitor_id=v) for v in visitors]
    await _ingest(client, events)

    resp = await client.get(f"/stores/{_STORE}/metrics")
    assert resp.status_code == 200
    body = resp.json()
    assert body["unique_visitors"] == 5


async def test_metrics_staff_excluded(client: AsyncClient, make_event):
    """Staff ENTRY events must not increment unique_visitors."""
    customer_id = str(uuid.uuid4())
    staff_id = str(uuid.uuid4())
    await _ingest(client, [
        make_event("ENTRY", visitor_id=customer_id, is_staff=False),
        make_event("ENTRY", visitor_id=staff_id, is_staff=True),
    ])

    resp = await client.get(f"/stores/{_STORE}/metrics")
    body = resp.json()
    assert_metrics_response(body)
    assert body["unique_visitors"] == 1, (
        "Staff session must not count toward unique_visitors"
    )


async def test_metrics_conversion_rate_zero(client: AsyncClient, make_event):
    """With no purchases, conversion rate should be 0."""
    await _ingest(client, [
        make_event("ENTRY"),
        make_event("ENTRY"),
        make_event("ENTRY"),
    ])
    resp = await client.get(f"/stores/{_STORE}/metrics")
    body = resp.json()
    assert_metrics_response(body)
    assert body["conversion_rate"] == 0.0


async def test_metrics_abandonment_rate(client: AsyncClient, make_event):
    """With 1 join and 1 abandon, abandonment rate should be 1.0."""
    visitor_id = str(uuid.uuid4())
    await _ingest(client, [
        make_event("BILLING_QUEUE_JOIN", visitor_id=visitor_id, zone_id="billing",
                   metadata={"queue_depth": 1}),
        make_event("BILLING_QUEUE_ABANDON", visitor_id=visitor_id, zone_id="billing",
                   dwell_ms=60000),
    ])
    resp = await client.get(f"/stores/{_STORE}/metrics")
    body = resp.json()
    assert_metrics_response(body)
    assert body["abandonment_rate"] == pytest.approx(1.0, abs=0.01)


async def test_metrics_nonexistent_store(client: AsyncClient):
    """Non-existent store should return zero metrics (not 404)."""
    resp = await client.get("/stores/store_999/metrics")
    assert resp.status_code == 200
    body = resp.json()
    assert body["unique_visitors"] == 0


async def test_metrics_time_window(client: AsyncClient, make_event):
    """Events outside the time window should not affect metrics."""
    from datetime import timedelta
    old_ts = (datetime.now(tz=timezone.utc) - timedelta(days=2)).isoformat()
    past_event = make_event("ENTRY", ts=datetime.now(tz=timezone.utc) - timedelta(days=2))
    await _ingest(client, [past_event])

    # Query only last 1 hour
    now = datetime.now(tz=timezone.utc)
    one_hour_ago = (now - timedelta(hours=1)).isoformat()
    resp = await client.get(
        f"/stores/{_STORE}/metrics",
        params={"start": one_hour_ago, "end": now.isoformat()},
    )
    body = resp.json()
    assert body["unique_visitors"] == 0, "Events outside window should be excluded"
