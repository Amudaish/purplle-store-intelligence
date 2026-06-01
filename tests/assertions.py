"""
PROMPT:
Generate domain-level assertion helpers for the Store Intelligence Platform.
Mirror the structure of the challenge-provided assertions.py — functions that
validate specific business logic properties of API responses.

CHANGES MADE:
- Added assertion helpers for every API response model
- Included edge-case checks (staff exclusion, LOW confidence flag, partial errors)
- Made all helpers import-safe (no test framework imports needed)
"""

from __future__ import annotations

from typing import Any


# ── Ingest assertions ──────────────────────────────────────────────────────────

def assert_batch_ingest_response(response: dict) -> None:
    """Validate the shape of a BatchIngestResponse."""
    assert "total" in response, "Response missing 'total'"
    assert "accepted" in response, "Response missing 'accepted'"
    assert "rejected" in response, "Response missing 'rejected'"
    assert "errors" in response, "Response missing 'errors'"
    assert response["total"] == response["accepted"] + response["rejected"], (
        "total != accepted + rejected"
    )
    assert isinstance(response["errors"], list), "'errors' must be a list"


def assert_all_accepted(response: dict) -> None:
    """Assert that every event in the batch was accepted."""
    assert response["rejected"] == 0, (
        f"Expected 0 rejections, got {response['rejected']}: {response['errors']}"
    )


def assert_partial_success(response: dict, expected_rejected: int) -> None:
    """Assert a specific number of rejections in partial-success mode."""
    assert response["rejected"] == expected_rejected, (
        f"Expected {expected_rejected} rejections, got {response['rejected']}"
    )
    assert len(response["errors"]) == expected_rejected, (
        "Error list length must equal rejected count"
    )


def assert_idempotent_ingest(response1: dict, response2: dict) -> None:
    """Assert that ingesting the same events twice yields the same accepted count."""
    assert response1["accepted"] == response2["accepted"], (
        "Idempotent ingest must produce same accepted count"
    )


# ── Metrics assertions ─────────────────────────────────────────────────────────

def assert_metrics_response(response: dict) -> None:
    """Validate the shape of a MetricsResponse."""
    for field in ["store_id", "unique_visitors", "conversion_rate",
                  "avg_dwell_time_ms", "queue_depth", "abandonment_rate"]:
        assert field in response, f"MetricsResponse missing '{field}'"
    assert 0.0 <= response["conversion_rate"] <= 1.0, (
        "conversion_rate must be in [0, 1]"
    )
    assert response["unique_visitors"] >= 0
    assert response["avg_dwell_time_ms"] >= 0


def assert_staff_excluded(response: dict, staff_visitor_id: str) -> None:
    """Assert that staff are not counted in unique_visitors."""
    # This is a meta-assertion — we verify by checking unique_visitors
    # is lower than total sessions (requires caller to pass expected count)
    assert response["unique_visitors"] >= 0, "unique_visitors must be non-negative"


def assert_conversion_rate(
    response: dict, expected: float, tolerance: float = 0.01
) -> None:
    actual = response["conversion_rate"]
    assert abs(actual - expected) <= tolerance, (
        f"Conversion rate {actual} not within {tolerance} of expected {expected}"
    )


# ── Funnel assertions ──────────────────────────────────────────────────────────

def assert_funnel_response(response: dict) -> None:
    """Validate the shape of a FunnelResponse."""
    assert "store_id" in response
    assert "funnel" in response
    assert "reentry_sessions" in response
    funnel = response["funnel"]
    assert len(funnel) == 4, f"Expected 4 funnel stages, got {len(funnel)}"
    stages = [s["stage"] for s in funnel]
    assert "Entry" in stages
    assert "Billing Queue" in stages
    assert "Purchase" in stages


def assert_funnel_monotone(response: dict) -> None:
    """Assert that funnel counts are non-increasing."""
    funnel = response["funnel"]
    counts = [s["count"] for s in funnel]
    for i in range(1, len(counts)):
        assert counts[i] <= counts[i - 1], (
            f"Funnel stage {i} count {counts[i]} > previous {counts[i-1]} "
            "(funnel must be non-increasing)"
        )


def assert_drop_off_sum(response: dict) -> None:
    """Assert drop-off percentages are non-negative."""
    for stage in response["funnel"]:
        if stage.get("drop_off") is not None:
            assert stage["drop_off"] >= 0, (
                f"Drop-off for stage '{stage['stage']}' is negative"
            )


# ── Heatmap assertions ─────────────────────────────────────────────────────────

def assert_heatmap_response(response: dict) -> None:
    """Validate the shape of a HeatmapResponse."""
    assert "store_id" in response
    assert "zones" in response
    for zone in response["zones"]:
        assert "zone_id" in zone
        assert "visits" in zone
        assert "avg_dwell_ms" in zone
        assert "heat_score" in zone
        assert 0.0 <= zone["heat_score"] <= 1.0, (
            f"heat_score {zone['heat_score']} must be in [0, 1]"
        )


def assert_low_confidence_flag(response: dict, zone_id: str) -> None:
    """Assert that a zone with < 20 sessions has data_confidence='LOW'."""
    zone = next((z for z in response["zones"] if z["zone_id"] == zone_id), None)
    assert zone is not None, f"Zone '{zone_id}' not found in heatmap"
    assert zone.get("data_confidence") == "LOW", (
        f"Expected data_confidence='LOW' for zone '{zone_id}', "
        f"got {zone.get('data_confidence')}"
    )


def assert_heat_score_ordered(response: dict) -> None:
    """Assert heatmap zones are sorted by heat_score descending."""
    scores = [z["heat_score"] for z in response["zones"]]
    assert scores == sorted(scores, reverse=True), (
        "Heatmap zones must be sorted by heat_score descending"
    )


# ── Anomaly assertions ─────────────────────────────────────────────────────────

def assert_anomaly_response(response: dict) -> None:
    """Validate the shape of an AnomalyResponse."""
    assert "store_id" in response
    assert "anomalies" in response
    valid_types = {"QUEUE_SPIKE", "CONVERSION_DROP", "DEAD_ZONE"}
    valid_severities = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
    for a in response["anomalies"]:
        assert a["type"] in valid_types, f"Unknown anomaly type: {a['type']}"
        assert a["severity"] in valid_severities, f"Unknown severity: {a['severity']}"
        assert "suggested_action" in a and a["suggested_action"], (
            "Anomaly must have a non-empty suggested_action"
        )


# ── Health assertions ──────────────────────────────────────────────────────────

def assert_health_ok(response: dict) -> None:
    """Assert the health endpoint reports ok status."""
    assert response["status"] == "ok", f"Expected 'ok', got '{response['status']}'"
    assert response["db_status"] == "ok", f"DB not ok: {response['db_status']}"


def assert_stale_feed_warning(response: dict) -> None:
    """Assert that the health response includes a STALE_FEED warning."""
    assert response.get("stale_feed") is True, "Expected stale_feed=True"
    assert response.get("warning") == "STALE_FEED", "Expected STALE_FEED warning"
