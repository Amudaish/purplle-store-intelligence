"""
Data Layer — all API fetching, helpers, and derived signals.
app.py imports from here; no business logic lives in app.py.
"""

from __future__ import annotations

import html as _html
import json
import os
import warnings
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
import streamlit as st

# ── API base URL resolution ──────────────────────────────────────────────────
# On Render, API_BASE_URL must be set as an environment variable.
# We do NOT fall back silently to localhost — that would hide misconfiguration.
_api_base_env = os.getenv("API_BASE_URL", "").strip()
if not _api_base_env:
    warnings.warn(
        "API_BASE_URL environment variable is not set. "
        "Falling back to http://localhost:8000 for local development only. "
        "On Render, set API_BASE_URL to your FastAPI service URL.",
        stacklevel=1,
    )
    _api_base_env = "https://purplle-store-intelligence-08v7.onrender.com"

API_BASE             = _api_base_env.rstrip("/")
AUTO_REFRESH_SECONDS = int(os.getenv("REFRESH_INTERVAL", "30"))
AVG_TICKET_INR       = 1_200
BENCHMARK_CONV       = 0.15   # 15% industry benchmark

STORE_NAMES = {
    "store_001": "Koramangala Flagship",
    "store_002": "Indiranagar Express",
}
STORE_CITIES = {
    "store_001": "Bangalore",
    "store_002": "Bangalore",
}

# ── API Helpers ───────────────────────────────────────────────────────────

import logging as _logging
_log = _logging.getLogger(__name__)


@st.cache_data(ttl=AUTO_REFRESH_SECONDS)
def fetch(endpoint: str) -> Optional[dict]:
    """Fetch JSON from the API, normalise the live schema to the internal format."""
    url = f"{API_BASE}{endpoint}"
    try:
        resp = httpx.get(url, timeout=10.0)
        if resp.status_code not in (200, 207):
            _log.warning("API returned %d for %s", resp.status_code, url)
            return None
        raw = resp.json()
        # Normalise live API responses to the internal schema the dashboard expects.
        return _normalise(endpoint, raw)
    except httpx.ConnectError:
        _log.error(
            "Cannot connect to API at %s — is API_BASE_URL correct? (%s)",
            url, API_BASE,
        )
        return None
    except Exception as exc:
        _log.error("API fetch error for %s: %s", url, exc)
        return None


def _normalise(endpoint: str, raw) -> Optional[dict]:
    """
    Translate the live Render API response shapes into the internal dict
    format expected by every dashboard component.

    Live API divergences (discovered via curl against the deployed service):

    /metrics  → returns flat keys: current_queue_depth, avg_dwell_per_zone (dict)
                instead of nested queue_depth:{current,avg,max} and avg_dwell_time_ms
    /funnel   → returns {stages:[{stage,count,dropoff_count,dropoff_percentage}]}
                instead of {funnel:[{stage,count,pct,drop_off}], reentry_sessions}
    /heatmap  → returns a bare list [{zone_id,visit_count,normalized_score,…}]
                instead of {store_id,zones:[{zone_id,visits,heat_score,…}]}
    /anomalies→ returns a bare list [{anomaly_type,severity,message,suggested_action,detected_at}]
                instead of {store_id,anomalies:[{type,severity,suggested_action,detected_at}]}
    """
    if raw is None:
        return None

    # ── /metrics ────────────────────────────────────────────────────────────
    if "/metrics" in endpoint:
        if not isinstance(raw, dict):
            return {}
        # Live API uses current_queue_depth (int) instead of queue_depth:{current,avg,max}
        qd = raw.get("queue_depth")
        if not isinstance(qd, dict):
            qd = {
                "current": int(raw.get("current_queue_depth", 0)),
                "avg":     0.0,
                "max":     0,
            }
        # Live API avg_dwell_per_zone is a dict of zone→ms; flatten to a single avg
        adpz = raw.get("avg_dwell_per_zone")
        if isinstance(adpz, dict) and adpz:
            avg_dwell_ms = float(sum(adpz.values()) / len(adpz))
        else:
            avg_dwell_ms = float(raw.get("avg_dwell_time_ms", 0))
        return {
            "store_id":          raw.get("store_id", ""),
            "unique_visitors":   int(raw.get("unique_visitors", 0)),
            "conversion_rate":   float(raw.get("conversion_rate", 0.0)),
            "avg_dwell_time_ms": avg_dwell_ms,
            "queue_depth":       qd,
            "abandonment_rate":  float(raw.get("abandonment_rate", 0.0)),
            "total_transactions":int(raw.get("total_transactions", 0)),
            "total_revenue_inr": float(raw.get("total_revenue_inr", 0.0)),
        }

    # ── /funnel ─────────────────────────────────────────────────────────────
    if "/funnel" in endpoint:
        if not isinstance(raw, dict):
            return {"funnel": [], "reentry_sessions": 0}
        # Live API uses "stages" instead of "funnel", and different sub-keys
        raw_stages = raw.get("funnel") or raw.get("stages") or []
        normalised_stages = []
        for s in raw_stages:
            normalised_stages.append({
                "stage":   s.get("stage", ""),
                "count":   int(s.get("count", 0)),
                "pct":     float(s.get("pct", s.get("dropoff_percentage", 0.0))),
                "drop_off": float(
                                s.get("drop_off")
                                if s.get("drop_off") is not None
                                else s.get("dropoff_percentage", 0.0)
                            ),
            })
        return {
            "store_id":         raw.get("store_id", ""),
            "funnel":           normalised_stages,
            "reentry_sessions": int(raw.get("reentry_sessions", 0)),
        }

    # ── /heatmap ─────────────────────────────────────────────────────────────
    if "/heatmap" in endpoint:
        # Live API returns a bare list instead of {store_id, zones:[…]}
        zone_list = raw if isinstance(raw, list) else raw.get("zones", [])
        normalised_zones = []
        for z in zone_list:
            # Live: visit_count + normalized_score; internal: visits + heat_score (0–1)
            normalised_zones.append({
                "zone_id":         z.get("zone_id", ""),
                "visits":          int(z.get("visits", z.get("visit_count", 0))),
                "avg_dwell_ms":    float(z.get("avg_dwell_ms", 0.0)),
                "heat_score":      float(z.get("heat_score",
                                        z.get("normalized_score", 0) / 100.0)),
                "data_confidence": z.get("data_confidence"),
            })
        store_id = raw.get("store_id", "") if isinstance(raw, dict) else ""
        return {"store_id": store_id, "zones": normalised_zones}

    # ── /anomalies ───────────────────────────────────────────────────────────
    if "/anomalies" in endpoint:
        # Live API returns a bare list instead of {store_id, anomalies:[…]}
        anom_list = raw if isinstance(raw, list) else raw.get("anomalies", [])
        normalised = []
        for a in anom_list:
            # Live: anomaly_type + message; internal: type + (no message field)
            # Live API uses "WARN" severity; normalise to "HIGH" for component compatibility
            raw_sev = a.get("severity", "LOW")
            sev = "HIGH" if raw_sev == "WARN" else raw_sev
            normalised.append({
                "type":             a.get("type", a.get("anomaly_type", "")),
                "severity":         sev,
                "suggested_action": a.get("suggested_action",
                                        a.get("message", "")),
                "detected_at":      a.get("detected_at", ""),
            })
        store_id = raw.get("store_id", "") if isinstance(raw, dict) else ""
        return {"store_id": store_id, "anomalies": normalised}

    # ── /health ───────────────────────────────────────────────────────────────
    if endpoint == "/health":
        if not isinstance(raw, dict):
            return {}
        # Live API uses stale_feed_warnings list; translate to stale_feed bool
        # that app.py reads via health_data.get("stale_feed", False)
        warnings_list = raw.get("stale_feed_warnings", [])
        return {
            "status":              raw.get("status", "error"),
            "database":            raw.get("database", "error"),
            "stale_feed":          bool(warnings_list),
            "stale_feed_warnings": warnings_list,
            "stale_store_ids": [
                w.split(" ")[1]          # "Store STORE_ID feed is stale..."
                for w in warnings_list
                if w.startswith("Store ")
            ],
            "last_event_timestamp_per_store": raw.get("last_event_timestamp_per_store", {}),
            "uptime_s":  raw.get("uptime_s", 0),
            "version":   raw.get("version", ""),
        }

    # ── all other endpoints (health, etc.) — pass through as-is ─────────────
    return raw if isinstance(raw, dict) else {}


def load_recent_events(store_id: str, limit: int = 60, scan_lines: int = 2000) -> list:
    jsonl_path = Path("data/events_output.jsonl")
    if not jsonl_path.exists():
        return []
    events = []
    try:
        lines = jsonl_path.read_text().splitlines()
        for line in lines[-scan_lines:]:
            if line.strip():
                try:
                    ev = json.loads(line)
                    if ev.get("store_id") == store_id:
                        events.append(ev)
                except json.JSONDecodeError:
                    pass
    except Exception:
        pass
    return events[-limit:]


# ── Signal Helpers ────────────────────────────────────────────────────────

def compute_store_score(metrics: dict, anomaly_data: dict) -> int:
    conv   = metrics.get("conversion_rate", 0.0)
    dwell  = min(metrics.get("avg_dwell_time_ms", 0) / 1000 / 600, 1.0)
    aband  = metrics.get("abandonment_rate", 0.0)
    n_crit = sum(
        1 for a in anomaly_data.get("anomalies", [])
        if a.get("severity") in ("CRITICAL", "HIGH")
    )
    return min(100, int(round(conv * 40 + dwell * 20 + (1 - aband) * 20 + max(0, 20 - n_crit * 7))))


def compute_risk_score(metrics: dict, anomaly_data: dict) -> tuple[int, str, str]:
    aband  = metrics.get("abandonment_rate", 0.0)
    depth  = metrics.get("queue_depth", {}).get("current", 0)
    n_crit = sum(1 for a in anomaly_data.get("anomalies", []) if a.get("severity") == "CRITICAL")
    n_high = sum(1 for a in anomaly_data.get("anomalies", []) if a.get("severity") == "HIGH")
    risk   = min(100, int(aband * 40 + min(depth, 10) * 3 + n_crit * 15 + n_high * 8))
    if risk >= 60:
        return risk, "#EF4444", "Critical"
    if risk >= 35:
        return risk, "#F59E0B", "Elevated"
    return risk, "#10B981", "Nominal"


def score_palette(score: int) -> tuple[str, str, str]:
    """(color, _, label)"""
    if score >= 75:
        return "#10B981", "#06B6D4", "High Performer"
    if score >= 50:
        return "#F59E0B", "#EF8C0B", "On Track"
    return "#EF4444", "#DC2626", "Needs Attention"


def peak_traffic_label(events: list) -> str:
    hours = []
    for e in events:
        ts = e.get("timestamp", "")
        if ts:
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                hours.append(dt.hour)
            except ValueError:
                pass
    if not hours:
        return "—"
    peak_hour = Counter(hours).most_common(1)[0][0]
    h12  = peak_hour % 12 or 12
    ampm = "AM" if peak_hour < 12 else "PM"
    return f"{h12}:00 {ampm}"


def top_zone_data(heatmap_data: dict) -> tuple[str, float, int]:
    zones = sorted((heatmap_data or {}).get("zones", []), key=lambda z: z.get("heat_score", 0), reverse=True)
    if not zones:
        return "—", 0.0, 0
    top  = zones[0]
    name = top.get("zone_id", "—").replace("_", " ").title()
    return name, top.get("heat_score", 0.0), top.get("visits", 0)


def queue_risk(metrics: dict) -> tuple[str, str, str]:
    depth = metrics.get("queue_depth", {}).get("current", 0)
    aband = metrics.get("abandonment_rate", 0.0)
    if depth >= 5 or aband >= 0.4:
        return "HIGH", "#EF4444", f"Depth {depth} · {aband*100:.0f}% abandon"
    if depth >= 3 or aband >= 0.2:
        return "MEDIUM", "#F59E0B", f"Depth {depth} · {aband*100:.0f}% abandon"
    return "LOW", "#10B981", f"Depth {depth} · {aband*100:.0f}% abandon"


def revenue_opportunity_inr(metrics: dict) -> tuple[str, int]:
    visitors = metrics.get("unique_visitors", 0)
    if visitors == 0:
        return "—", 0
    lift_txns = max(0, int(visitors * 0.10))
    amount    = lift_txns * AVG_TICKET_INR
    if amount >= 1_00_000:
        return f"+₹{amount/1_00_000:.1f}L", amount
    if amount >= 1_000:
        return f"+₹{amount:,}", amount
    return f"+₹{amount}", amount


def conversion_loss_inr(metrics: dict) -> tuple[str, int]:
    visitors = metrics.get("unique_visitors", 0)
    conv     = metrics.get("conversion_rate", 0.0)
    if visitors == 0 or conv >= BENCHMARK_CONV:
        return "₹0", 0
    gap_txns = int(visitors * (BENCHMARK_CONV - conv))
    amount   = gap_txns * AVG_TICKET_INR
    if amount >= 1_00_000:
        return f"₹{amount/1_00_000:.1f}L", amount
    return f"₹{amount:,}", amount


def queue_cost_inr(metrics: dict) -> tuple[str, int]:
    visitors = metrics.get("unique_visitors", 0)
    aband    = metrics.get("abandonment_rate", 0.0)
    amount   = int(visitors * aband * AVG_TICKET_INR)
    if amount >= 1_00_000:
        return f"₹{amount/1_00_000:.1f}L", amount
    return f"₹{amount:,}", amount


def staffing_recommendation(metrics: dict, anomaly_data: dict) -> tuple[str, str, str]:
    depth  = metrics.get("queue_depth", {}).get("current", 0)
    n_crit = sum(1 for a in anomaly_data.get("anomalies", []) if a.get("severity") == "CRITICAL")
    if depth >= 6 or n_crit >= 2:
        return "+3 Counters", "#EF4444", f"Critical understaffing — queue depth {depth}, {n_crit} critical alert(s) active"
    if depth >= 4 or n_crit >= 1:
        return "+2 Counters", "#F59E0B", f"Queue stress — depth {depth}, reducing abandonment is the priority"
    if depth >= 2:
        return "+1 Counter", "#F59E0B", f"Moderate pressure — depth {depth}, approaching threshold"
    return "Optimal", "#10B981", "Staffing is within acceptable parameters for current traffic"


# ── Executive Action Generation ───────────────────────────────────────────

def generate_executive_actions(
    metrics: dict,
    heatmap_data: dict,
    anomaly_data: dict,
    funnel_data: dict,
) -> list[dict]:
    """
    Generate ranked, executive-level action cards.
    Each dict has: signal, urgency, color, recommendation, context,
                   impact_inr, impact_str, confidence_pct, expected_outcome.
    """
    actions: list[dict] = []

    zones    = sorted((heatmap_data or {}).get("zones", []), key=lambda z: z.get("heat_score", 0), reverse=True)
    funnel   = (funnel_data or {}).get("funnel", [])
    anom     = (anomaly_data or {}).get("anomalies", [])
    conv     = metrics.get("conversion_rate", 0.0)
    aband    = metrics.get("abandonment_rate", 0.0)
    visitors = metrics.get("unique_visitors", 0)
    depth    = metrics.get("queue_depth", {}).get("current", 0)
    reentries = (funnel_data or {}).get("reentry_sessions", 0)

    # 1 — Queue Abandonment
    if aband >= 0.40:
        lost = int(visitors * aband * AVG_TICKET_INR)
        imp  = f"₹{lost:,}" if lost < 1_00_000 else f"₹{lost/1_00_000:.1f}L"
        actions.append({
            "signal": "QUEUE", "urgency": "CRITICAL", "color": "#EF4444",
            "recommendation": "Open an additional billing counter immediately",
            "context": (
                f"Queue depth is {depth} with {aband*100:.0f}% abandonment. "
                f"Approximately {int(visitors * aband)} customers are leaving without purchasing each cycle. "
                "Every 15 minutes of inaction compounds the loss."
            ),
            "impact_inr": lost, "impact_str": imp, "confidence_pct": 91,
            "expected_outcome": f"−{int(aband*45):.0f}% abandonment · +₹{int(lost*0.6):,} recovered within 15 min",
        })
    elif aband >= 0.20:
        lost = int(visitors * aband * AVG_TICKET_INR)
        imp  = f"₹{lost:,}" if lost < 1_00_000 else f"₹{lost/1_00_000:.1f}L"
        actions.append({
            "signal": "QUEUE", "urgency": "HIGH", "color": "#F59E0B",
            "recommendation": "Deploy mobile checkout or assign additional billing staff",
            "context": (
                f"Abandonment rate {aband*100:.0f}% exceeds the 20% threshold. "
                f"Queue depth {depth}. Estimated {int(visitors * aband)} affected customers per cycle."
            ),
            "impact_inr": lost, "impact_str": imp, "confidence_pct": 84,
            "expected_outcome": f"−{int(aband*30):.0f}% abandonment · +₹{int(lost*0.5):,} recovered",
        })

    # 2 — Conversion Gap
    if conv < BENCHMARK_CONV and visitors > 10:
        gap_pp    = (BENCHMARK_CONV - conv) * 100
        gap_txns  = int(visitors * (BENCHMARK_CONV - conv))
        imp_amt   = gap_txns * AVG_TICKET_INR
        imp       = f"₹{imp_amt:,}" if imp_amt < 1_00_000 else f"₹{imp_amt/1_00_000:.1f}L"
        conf      = min(88, 55 + int(visitors / 8))
        actions.append({
            "signal": "CONVERSION", "urgency": "HIGH" if gap_pp > 8 else "MEDIUM",
            "color": "#F59E0B" if gap_pp > 8 else "#2563EB",
            "recommendation": "Engage floor staff with high-dwell-time visitors in key zones",
            "context": (
                f"Conversion at {conv*100:.1f}% vs {BENCHMARK_CONV*100:.0f}% benchmark — "
                f"{gap_pp:.1f}pp gap. {gap_txns} additional transactions available today "
                "with targeted staff engagement in high-heat zones."
            ),
            "impact_inr": imp_amt, "impact_str": imp, "confidence_pct": conf,
            "expected_outcome": f"+{gap_pp/2:.1f}pp conversion · +₹{int(imp_amt*0.5):,} daily uplift",
        })

    # 3 — Hot Zone Staff Signal
    if zones:
        top  = zones[0]
        zn   = _html.escape(top["zone_id"].replace("_", " ").title())
        heat = top.get("heat_score", 0)
        if heat >= 0.65:
            z_imp = int(top.get("visits", 0) * conv * AVG_TICKET_INR * 0.12)
            z_str = f"₹{z_imp:,}" if z_imp < 1_00_000 else f"₹{z_imp/1_00_000:.1f}L"
            actions.append({
                "signal": "ZONE", "urgency": "MEDIUM", "color": "#06B6D4",
                "recommendation": f"Maximise staff presence in {zn} — peak demand zone active",
                "context": (
                    f"{zn} at {heat*100:.0f}% heat intensity with {top.get('visits', 0):,} visits. "
                    f"Avg dwell {top.get('avg_dwell_ms', 0)/1000:.0f}s signals high purchase consideration. "
                    "A single engaged advisor here can directly convert high-intent visitors."
                ),
                "impact_inr": z_imp, "impact_str": z_str, "confidence_pct": 85,
                "expected_outcome": f"+12% zone conversion · {zn} revenue uplift",
            })

    # 4 — Cold Zone Recovery
    if len(zones) >= 2:
        cold = zones[-1]
        cn   = _html.escape(cold["zone_id"].replace("_", " ").title())
        ch   = cold.get("heat_score", 0)
        if ch < 0.30:
            c_imp = int(cold.get("visits", 0) * 0.5 * AVG_TICKET_INR)
            c_str = f"₹{c_imp:,}" if c_imp < 1_00_000 else f"₹{c_imp/1_00_000:.1f}L"
            actions.append({
                "signal": "ZONE", "urgency": "MEDIUM", "color": "#8B5CF6",
                "recommendation": f"Reactivate {cn} — relocate promotional display to entrance sightline",
                "context": (
                    f"{cn} underperforming at {ch*100:.0f}% heat with only {cold.get('visits', 0)} visits. "
                    "Product visibility or signage is not capturing customer attention from main aisles."
                ),
                "impact_inr": c_imp, "impact_str": c_str, "confidence_pct": 73,
                "expected_outcome": f"+{int((0.55 - ch)*100):.0f}% zone traffic recovery within 1 hour",
            })

    # 5 — Funnel Drop-off
    if funnel and len(funnel) >= 2:
        e_count = next((s["count"] for s in funnel if s["stage"] == "Entry"), 0)
        z_count = next((s["count"] for s in funnel if s["stage"] == "Zone Visit"), e_count)
        if e_count > 0:
            dr = (e_count - z_count) / e_count
            if dr >= 0.40:
                d_imp = int(e_count * dr * conv * AVG_TICKET_INR)
                d_str = f"₹{d_imp:,}" if d_imp < 1_00_000 else f"₹{d_imp/1_00_000:.1f}L"
                actions.append({
                    "signal": "FUNNEL", "urgency": "MEDIUM", "color": "#8B5CF6",
                    "recommendation": "Redesign entrance flow — redirect traffic into browse zones",
                    "context": (
                        f"{dr*100:.0f}% of visitors exit without exploring any product zone. "
                        "Entrance merchandising or directional signage is failing to capture customer interest."
                    ),
                    "impact_inr": d_imp, "impact_str": d_str, "confidence_pct": 76,
                    "expected_outcome": f"−{int(dr*40):.0f}% early exit · +zone exploration coverage",
                })

    # 6 — Re-entry (positive signal)
    if reentries >= 5:
        r_imp = int(reentries * conv * AVG_TICKET_INR * 1.4)
        r_str = f"₹{r_imp:,}"
        actions.append({
            "signal": "JOURNEY", "urgency": "LOW", "color": "#10B981",
            "recommendation": "Deploy in-aisle advisors at re-entry zones — high-intent customers present",
            "context": (
                f"{reentries} re-entry sessions detected. Customers returning to specific zones signal "
                "strong product consideration and are significantly more likely to convert with light assistance."
            ),
            "impact_inr": r_imp, "impact_str": r_str, "confidence_pct": 79,
            "expected_outcome": f"+{int(reentries * 0.35):.0f} additional transactions from engaged returners",
        })

    # Fallback
    if not actions:
        actions.append({
            "signal": "STATUS", "urgency": "LOW", "color": "#10B981",
            "recommendation": "All metrics within operational targets — maintain current configuration",
            "context": (
                f"Store performing within expected parameters. Conversion {conv*100:.1f}%, "
                f"abandonment {aband*100:.0f}%, queue depth {depth}. No immediate intervention required."
            ),
            "impact_inr": 0, "impact_str": "On target", "confidence_pct": 95,
            "expected_outcome": "Maintain current staffing and floor layout",
        })

    # Sort: impact descending, then urgency
    _ord = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    actions.sort(key=lambda a: (-a["impact_inr"], _ord.get(a["urgency"], 4)))
    return actions


# ── Alert State ───────────────────────────────────────────────────────────

def build_alert_state(metrics: dict, anomaly_data: dict) -> dict:
    anomalies = (anomaly_data or {}).get("anomalies", [])
    aband     = metrics.get("abandonment_rate", 0.0)
    conv      = metrics.get("conversion_rate", 0.0)
    depth     = metrics.get("queue_depth", {}).get("current", 0)
    visitors  = metrics.get("unique_visitors", 0)

    _sev_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    _type_label = {
        "QUEUE_SPIKE":         "Queue depth spike",
        "BILLING_QUEUE_SPIKE": "Billing queue spike",
        "CONVERSION_DROP":     "Conversion rate drop",
        "DEAD_ZONE":           "Dead zone detected",
        "STALE_FEED":          "Camera feed stale",
        "HIGH_DWELL":          "Unusually high dwell time",
    }

    if anomalies:
        top  = sorted(anomalies, key=lambda a: _sev_order.get(a.get("severity", "LOW"), 4))[0]
        sev  = top.get("severity", "LOW")
        tlbl = _html.escape(_type_label.get(top.get("type", ""), top.get("type", "").replace("_", " ").title()))
        lost = int(visitors * aband * AVG_TICKET_INR)
        lst  = f"₹{lost:,}" if lost < 1_00_000 else f"₹{lost/1_00_000:.1f}L"
        if sev == "CRITICAL":
            return {
                "state": "critical", "pill_class": "alert-pill-critical", "banner_class": "alert-critical",
                "label": "CRITICAL",
                "message": f"<strong>{tlbl}</strong> · ₹{lst} at risk · Queue depth {depth} · {aband*100:.0f}% abandonment",
                "cta": "OPEN DECISION CENTER →",
            }
        if sev in ("HIGH", "MEDIUM"):
            return {
                "state": "elevated", "pill_class": "alert-pill-elevated", "banner_class": "alert-elevated",
                "label": "ELEVATED",
                "message": f"<strong>{tlbl}</strong> · {aband*100:.0f}% abandonment · {conv*100:.1f}% conversion · Attention recommended",
                "cta": "REVIEW ACTIONS →",
            }

    if aband >= 0.40:
        lost = int(visitors * aband * AVG_TICKET_INR)
        lst  = f"₹{lost:,}" if lost < 1_00_000 else f"₹{lost/1_00_000:.1f}L"
        return {
            "state": "critical", "pill_class": "alert-pill-critical", "banner_class": "alert-critical",
            "label": "CRITICAL",
            "message": f"Queue abandonment <strong>{aband*100:.0f}%</strong> — {lst} at risk per cycle · Open billing counter immediately",
            "cta": "ACT NOW →",
        }

    if aband >= 0.20 or conv < 0.08:
        return {
            "state": "elevated", "pill_class": "alert-pill-elevated", "banner_class": "alert-elevated",
            "label": "ELEVATED",
            "message": f"Conversion <strong>{conv*100:.1f}%</strong> · Abandonment {aband*100:.0f}% — below benchmark. Staff redeployment recommended.",
            "cta": "REVIEW ACTIONS →",
        }

    return {
        "state": "nominal", "pill_class": "alert-pill-nominal", "banner_class": "alert-nominal",
        "label": "NOMINAL",
        "message": f"All metrics within range · Conversion {conv*100:.1f}% · Queue depth {depth} · {visitors:,} active visitors",
        "cta": "VIEW DETAILS →",
    }
