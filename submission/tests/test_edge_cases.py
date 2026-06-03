"""
PROMPT:
Generate edge-case tests for the Store Intelligence API covering all 6
edge cases from the challenge spec:
1. Group entry — multiple visitors arriving simultaneously
2. Staff exclusion — staff events excluded from all analytics
3. Re-entry — same visitor leaving and returning
4. Partial occlusion — low-confidence events still processed
5. Billing queue buildup — queue depth tracked correctly
6. Camera overlap — same visitor_id from multiple cameras deduplicated

CHANGES MADE:
- Covered all 6 edge cases from challenge_requirements.md
- Group entry tested by ingesting simultaneous ENTRY events with different visitor_ids
- Re-entry tested via ENTRY→EXIT→REENTRY event sequence
- Camera overlap simulated by using same visitor_id across different camera_ids
- Low confidence events accepted but stored with actual confidence value
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

_STORE = "store_001"


async def _ingest(client, events):
    r = await client.post("/events/ingest", json={"events": events})
    assert r.status_code in (200, 207)
    return r.json()


# ── 1. Group Entry ─────────────────────────────────────────────────────────────

async def test_group_entry_counts_individuals(client: AsyncClient, make_event):
    """
    Group of 4 people arriving simultaneously should count as 4 unique visitors.
    (Groups are detected as individual bounding boxes by the CV pipeline.)
    """
    group_size = 4
    ts = datetime.now(tz=timezone.utc)
    events = [
        make_event("ENTRY", visitor_id=str(uuid.uuid4()), ts=ts)
        for _ in range(group_size)
    ]
    await _ingest(client, events)

    resp = await client.get(f"/stores/{_STORE}/metrics")
    body = resp.json()
    assert body["unique_visitors"] == group_size, (
        f"Group of {group_size} should produce {group_size} unique visitors"
    )


# ── 2. Staff Exclusion ─────────────────────────────────────────────────────────

async def test_staff_excluded_from_metrics(client: AsyncClient, make_event):
    """Staff events must be excluded from unique_visitors and funnel."""
    customer_id = str(uuid.uuid4())
    staff_id = str(uuid.uuid4())
    await _ingest(client, [
        make_event("ENTRY", visitor_id=customer_id, is_staff=False),
        make_event("ENTRY", visitor_id=staff_id, is_staff=True),
        make_event("ZONE_ENTER", visitor_id=staff_id, zone_id="cosmetics", is_staff=True),
        make_event("BILLING_QUEUE_JOIN", visitor_id=staff_id, zone_id="billing", is_staff=True),
    ])

    # Metrics
    metrics_resp = await client.get(f"/stores/{_STORE}/metrics")
    metrics = metrics_resp.json()
    assert metrics["unique_visitors"] == 1, "Only 1 customer should be counted"

    # Funnel
    funnel_resp = await client.get(f"/stores/{_STORE}/funnel")
    funnel = funnel_resp.json()
    billing_stage = next(s for s in funnel["funnel"] if s["stage"] == "Billing Queue")
    assert billing_stage["count"] == 0, "Staff billing events must not appear in funnel"


async def test_staff_excluded_from_heatmap(client: AsyncClient, make_event):
    """Staff zone events must not appear in heatmap."""
    await _ingest(client, [
        make_event("ZONE_ENTER", zone_id="fragrance", is_staff=True),
    ])
    resp = await client.get(f"/stores/{_STORE}/heatmap")
    body = resp.json()
    fragrance = next((z for z in body["zones"] if z["zone_id"] == "fragrance"), None)
    if fragrance:
        assert fragrance["visits"] == 0


# ── 3. Re-Entry ────────────────────────────────────────────────────────────────

async def test_reentry_event_accepted(client: AsyncClient, make_event):
    """REENTRY event should be accepted and counted in reentry_sessions funnel field."""
    visitor_id = str(uuid.uuid4())
    await _ingest(client, [
        make_event("ENTRY", visitor_id=visitor_id),
        make_event("EXIT", visitor_id=visitor_id),
        make_event("REENTRY", visitor_id=visitor_id),
    ])

    funnel_resp = await client.get(f"/stores/{_STORE}/funnel")
    funnel = funnel_resp.json()
    assert funnel["reentry_sessions"] >= 1, (
        "REENTRY event must increment reentry_sessions"
    )


async def test_reentry_still_counted_as_visitor(client: AsyncClient, make_event):
    """Visitor who re-enters should still count as 1 unique visitor, not 2."""
    visitor_id = str(uuid.uuid4())
    await _ingest(client, [
        make_event("ENTRY", visitor_id=visitor_id),
        make_event("EXIT", visitor_id=visitor_id),
        make_event("REENTRY", visitor_id=visitor_id),
        make_event("EXIT", visitor_id=visitor_id),
    ])
    metrics_resp = await client.get(f"/stores/{_STORE}/metrics")
    metrics = metrics_resp.json()
    assert metrics["unique_visitors"] == 1, (
        "Visitor who re-enters counts as 1 unique visitor (by visitor_id)"
    )


# ── 4. Partial Occlusion (low confidence) ─────────────────────────────────────

async def test_low_confidence_events_accepted(client: AsyncClient, make_batch):
    """Low-confidence events (≥0.0) should be accepted and stored."""
    low_conf_event = {
        "event_id": str(uuid.uuid4()),
        "store_id": _STORE,
        "camera_id": "cam_floor",
        "visitor_id": str(uuid.uuid4()),
        "event_type": "ZONE_ENTER",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "zone_id": "cosmetics",
        "dwell_ms": None,
        "is_staff": False,
        "confidence": 0.10,   # very low but valid
        "metadata": {"occlusion": "partial"},
    }
    resp = await client.post("/events/ingest", json=make_batch([low_conf_event]))
    body = resp.json()
    assert body["accepted"] == 1, "Low-confidence events must still be accepted"


# ── 5. Billing Queue Buildup ───────────────────────────────────────────────────

async def test_billing_queue_buildup(client: AsyncClient, make_event):
    """Multiple visitors in billing zone should increment queue depth in metrics."""
    visitors = [str(uuid.uuid4()) for _ in range(3)]
    events = []
    for i, vid in enumerate(visitors):
        events.append(
            {**make_event("BILLING_QUEUE_JOIN", visitor_id=vid, zone_id="billing"),
             "metadata": {"queue_depth": i + 1}}
        )
    await _ingest(client, events)

    metrics_resp = await client.get(f"/stores/{_STORE}/metrics")
    metrics = metrics_resp.json()
    # Max queue depth should be at least 3
    assert metrics["queue_depth"]["max"] >= 3


async def test_billing_queue_abandon_event(client: AsyncClient, make_event):
    """BILLING_QUEUE_ABANDON must be accepted and contribute to abandonment_rate."""
    visitor_id = str(uuid.uuid4())
    await _ingest(client, [
        {**make_event("BILLING_QUEUE_JOIN", visitor_id=visitor_id, zone_id="billing"),
         "metadata": {"queue_depth": 1}},
        make_event("BILLING_QUEUE_ABANDON", visitor_id=visitor_id, zone_id="billing",
                   dwell_ms=90000),
    ])
    metrics_resp = await client.get(f"/stores/{_STORE}/metrics")
    metrics = metrics_resp.json()
    assert metrics["abandonment_rate"] > 0, (
        "BILLING_QUEUE_ABANDON must contribute to abandonment_rate"
    )


# ── 6. Camera Overlap (cross-camera deduplication) ────────────────────────────

async def test_cross_camera_same_visitor_id(client: AsyncClient, make_event):
    """
    Same visitor_id seen by multiple cameras should count as 1 unique visitor.
    (Re-ID deduplication is done in the pipeline; API receives same visitor_id.)
    """
    visitor_id = str(uuid.uuid4())
    await _ingest(client, [
        make_event("ENTRY", visitor_id=visitor_id, camera_id="cam_entry"),
        make_event("ZONE_ENTER", visitor_id=visitor_id, camera_id="cam_floor",
                   zone_id="cosmetics"),
        make_event("BILLING_QUEUE_JOIN", visitor_id=visitor_id, camera_id="cam_billing",
                   zone_id="billing"),
    ])
    metrics_resp = await client.get(f"/stores/{_STORE}/metrics")
    metrics = metrics_resp.json()
    assert metrics["unique_visitors"] == 1, (
        "Same visitor_id across multiple cameras = 1 unique visitor"
    )
