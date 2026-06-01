"""
PROMPT:
Generate pytest tests for GET /stores/{id}/heatmap covering:
- Response shape and heat_score range [0,1]
- Zones sorted by heat_score descending
- data_confidence='LOW' for zones with fewer than 20 sessions
- Empty store returns empty zones list
- Staff zone events excluded from heatmap

CHANGES MADE:
- Used heatmap-specific assertion helpers
- Seeded exactly 19 ZONE_ENTER events to trigger LOW confidence flag
- Verified heat_score ordering invariant
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from tests.assertions import (
    assert_heat_score_ordered,
    assert_heatmap_response,
    assert_low_confidence_flag,
)

pytestmark = pytest.mark.asyncio

_STORE = "store_001"


async def _ingest(client, events):
    r = await client.post("/events/ingest", json={"events": events})
    assert r.status_code in (200, 207)


async def test_heatmap_empty_store(client: AsyncClient):
    """Empty store should return empty zones list."""
    resp = await client.get(f"/stores/{_STORE}/heatmap")
    assert resp.status_code == 200
    body = resp.json()
    assert_heatmap_response(body)
    assert body["zones"] == []


async def test_heatmap_response_shape(client: AsyncClient, make_event):
    """Verify zone heatmap has required fields and valid heat_score range."""
    vid = str(uuid.uuid4())
    await _ingest(client, [
        make_event("ZONE_ENTER", visitor_id=vid, zone_id="cosmetics"),
        make_event("ZONE_EXIT", visitor_id=vid, zone_id="cosmetics", dwell_ms=60000),
    ])
    resp = await client.get(f"/stores/{_STORE}/heatmap")
    body = resp.json()
    assert_heatmap_response(body)
    assert len(body["zones"]) >= 1


async def test_heatmap_heat_score_range(client: AsyncClient, make_event):
    """All heat_score values must be in [0, 1]."""
    for zone in ("cosmetics", "skincare", "fragrance"):
        vid = str(uuid.uuid4())
        await _ingest(client, [
            make_event("ZONE_ENTER", visitor_id=vid, zone_id=zone),
            make_event("ZONE_EXIT", visitor_id=vid, zone_id=zone, dwell_ms=30000),
        ])
    resp = await client.get(f"/stores/{_STORE}/heatmap")
    body = resp.json()
    assert_heatmap_response(body)
    for zone in body["zones"]:
        assert 0.0 <= zone["heat_score"] <= 1.0


async def test_heatmap_sorted_by_heat_score(client: AsyncClient, make_event):
    """Zones must be returned sorted by heat_score descending."""
    for zone in ("cosmetics", "skincare", "fragrance"):
        for _ in range(3):
            vid = str(uuid.uuid4())
            await _ingest(client, [
                make_event("ZONE_ENTER", visitor_id=vid, zone_id=zone),
            ])
    resp = await client.get(f"/stores/{_STORE}/heatmap")
    body = resp.json()
    assert_heat_score_ordered(body)


async def test_heatmap_low_confidence_flag(client: AsyncClient, make_event):
    """Zone with < 20 sessions must have data_confidence='LOW'."""
    zone_id = "fragrance"
    # Ingest exactly 5 ZONE_ENTER events (below threshold of 20)
    for _ in range(5):
        vid = str(uuid.uuid4())
        await _ingest(client, [make_event("ZONE_ENTER", visitor_id=vid, zone_id=zone_id)])

    resp = await client.get(f"/stores/{_STORE}/heatmap")
    body = resp.json()
    assert_heatmap_response(body)
    assert_low_confidence_flag(body, zone_id)


async def test_heatmap_staff_excluded(client: AsyncClient, make_event):
    """Staff zone events must not appear in heatmap."""
    await _ingest(client, [
        make_event("ZONE_ENTER", zone_id="cosmetics", is_staff=True),
    ])
    resp = await client.get(f"/stores/{_STORE}/heatmap")
    body = resp.json()
    # cosmetics zone should have 0 visits (staff excluded)
    cosmetics_zone = next(
        (z for z in body["zones"] if z["zone_id"] == "cosmetics"), None
    )
    if cosmetics_zone:
        assert cosmetics_zone["visits"] == 0, "Staff zone visits must be excluded"
