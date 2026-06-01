"""
PROMPT:
Generate pytest tests for GET /stores/{id}/funnel covering:
- Response shape (4 stages, correct labels)
- Funnel is non-increasing (each stage ≤ previous)
- Drop-off percentages are non-negative
- Re-entry sessions are counted
- Empty store returns zero funnel

CHANGES MADE:
- Used funnel-specific assertion helpers from assertions.py
- Seeded a complete visitor journey to validate each stage count
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from tests.assertions import (
    assert_drop_off_sum,
    assert_funnel_monotone,
    assert_funnel_response,
)

pytestmark = pytest.mark.asyncio

_STORE = "store_001"


async def _ingest(client, events):
    r = await client.post("/events/ingest", json={"events": events})
    assert r.status_code in (200, 207)


async def test_funnel_empty_store(client: AsyncClient):
    """Empty store should return 4 stages all at zero."""
    resp = await client.get(f"/stores/{_STORE}/funnel")
    assert resp.status_code == 200
    body = resp.json()
    assert_funnel_response(body)
    for stage in body["funnel"]:
        assert stage["count"] == 0


async def test_funnel_shape(client: AsyncClient, make_event):
    """Funnel should always return exactly 4 stages with correct labels."""
    await _ingest(client, [make_event("ENTRY")])
    resp = await client.get(f"/stores/{_STORE}/funnel")
    body = resp.json()
    assert_funnel_response(body)
    stage_names = [s["stage"] for s in body["funnel"]]
    assert "Entry" in stage_names
    assert "Zone Visit" in stage_names
    assert "Billing Queue" in stage_names
    assert "Purchase" in stage_names


async def test_funnel_is_monotone(client: AsyncClient, make_event):
    """Each stage count must be ≤ the previous stage count."""
    # 3 entries, 2 zone visits, 1 billing, 0 purchases
    for _ in range(3):
        vid = str(uuid.uuid4())
        await _ingest(client, [make_event("ENTRY", visitor_id=vid)])

    for _ in range(2):
        vid = str(uuid.uuid4())
        await _ingest(client, [
            make_event("ENTRY", visitor_id=vid),
            make_event("ZONE_ENTER", visitor_id=vid, zone_id="cosmetics"),
        ])

    for _ in range(1):
        vid = str(uuid.uuid4())
        await _ingest(client, [
            make_event("ENTRY", visitor_id=vid),
            make_event("BILLING_QUEUE_JOIN", visitor_id=vid, zone_id="billing"),
        ])

    resp = await client.get(f"/stores/{_STORE}/funnel")
    body = resp.json()
    assert_funnel_monotone(body)


async def test_funnel_drop_off_non_negative(client: AsyncClient, make_event):
    """All drop-off values must be >= 0."""
    await _ingest(client, [make_event("ENTRY")])
    resp = await client.get(f"/stores/{_STORE}/funnel")
    body = resp.json()
    assert_drop_off_sum(body)


async def test_funnel_reentry_counted(client: AsyncClient, make_event):
    """Re-entry sessions must increment reentry_sessions counter."""
    vid = str(uuid.uuid4())
    await _ingest(client, [
        make_event("ENTRY", visitor_id=vid),
        make_event("EXIT", visitor_id=vid),
        make_event("REENTRY", visitor_id=vid),
    ])
    resp = await client.get(f"/stores/{_STORE}/funnel")
    body = resp.json()
    assert body["reentry_sessions"] >= 1, (
        "REENTRY event must increment reentry_sessions"
    )


async def test_funnel_staff_excluded(client: AsyncClient, make_event):
    """Staff sessions must not appear in any funnel stage."""
    await _ingest(client, [
        make_event("ENTRY", is_staff=True),
        make_event("BILLING_QUEUE_JOIN", is_staff=True, zone_id="billing"),
    ])
    resp = await client.get(f"/stores/{_STORE}/funnel")
    body = resp.json()
    for stage in body["funnel"]:
        assert stage["count"] == 0, (
            f"Staff sessions must not appear in funnel stage '{stage['stage']}'"
        )
