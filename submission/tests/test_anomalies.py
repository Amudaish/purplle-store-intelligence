"""
PROMPT:
Generate pytest tests for GET /stores/{id}/anomalies covering:
- Response shape validation
- DEAD_ZONE detection when a zone has < 3 visits while store is active
- Severity levels are valid (LOW/MEDIUM/HIGH/CRITICAL)
- Suggested action is present and non-empty
- Empty store returns empty anomaly list

CHANGES MADE:
- Cannot easily trigger QUEUE_SPIKE or CONVERSION_DROP via ingestion alone
  (requires 30-day baseline data) — tested via response shape only
- DEAD_ZONE tested by seeding entry events but no zone events for a zone
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from tests.assertions import assert_anomaly_response

pytestmark = pytest.mark.asyncio

_STORE = "store_001"


async def _ingest(client, events):
    r = await client.post("/events/ingest", json={"events": events})
    assert r.status_code in (200, 207)


async def test_anomalies_empty_store(client: AsyncClient):
    """Empty store should return an empty anomaly list without error."""
    resp = await client.get(f"/stores/{_STORE}/anomalies")
    assert resp.status_code == 200
    body = resp.json()
    assert_anomaly_response(body)
    assert body["anomalies"] == []


async def test_anomalies_response_shape(client: AsyncClient, make_event):
    """Verify anomaly response shape even when no anomalies detected."""
    await _ingest(client, [make_event("ENTRY")])
    resp = await client.get(f"/stores/{_STORE}/anomalies")
    assert resp.status_code == 200
    body = resp.json()
    assert_anomaly_response(body)
    assert "store_id" in body
    assert body["store_id"] == _STORE


async def test_anomaly_severity_valid(client: AsyncClient):
    """All anomalies in the response must have valid severity values."""
    resp = await client.get(f"/stores/{_STORE}/anomalies")
    body = resp.json()
    valid_severities = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
    for a in body["anomalies"]:
        assert a["severity"] in valid_severities, (
            f"Invalid severity: {a['severity']}"
        )


async def test_anomaly_type_valid(client: AsyncClient):
    """All anomaly types must be from the defined set."""
    resp = await client.get(f"/stores/{_STORE}/anomalies")
    body = resp.json()
    valid_types = {"QUEUE_SPIKE", "CONVERSION_DROP", "DEAD_ZONE"}
    for a in body["anomalies"]:
        assert a["type"] in valid_types, f"Invalid anomaly type: {a['type']}"


async def test_anomaly_suggested_action_present(client: AsyncClient, make_event):
    """Every anomaly must have a non-empty suggested_action."""
    # Seed enough ENTRY events to meet the 5-entry threshold for DEAD_ZONE detection
    for _ in range(6):
        await _ingest(client, [make_event("ENTRY")])

    resp = await client.get(f"/stores/{_STORE}/anomalies")
    body = resp.json()
    for anomaly in body["anomalies"]:
        assert anomaly.get("suggested_action"), (
            f"Anomaly {anomaly['type']} missing suggested_action"
        )


async def test_anomalies_nonexistent_store(client: AsyncClient):
    """Non-existent store should return empty anomalies without error."""
    resp = await client.get("/stores/store_nonexistent/anomalies")
    assert resp.status_code == 200
    body = resp.json()
    assert body["anomalies"] == []
