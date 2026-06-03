"""
Apex Retail Intelligence — Command Center
Main application entry point. Layout only; all logic lives in data_layer.py.
"""

from __future__ import annotations

import html as _html
import time

import streamlit as st

import design_system
from data_layer import (
    AUTO_REFRESH_SECONDS,
    STORE_NAMES,
    build_alert_state,
    compute_store_score,
    fetch,
    load_recent_events,
    peak_traffic_label,
    score_palette,
    top_zone_data,
)
from components.floor_intelligence import render_floor_intelligence
from components.ai_action_center   import render_ai_action_center
from components.revenue_pulse      import render_revenue_pulse
from components.journey_tab        import render_journey_tab
from components.queue_tab          import render_queue_tab
from components.risk_tab           import render_risk_tab

# ── Page Config ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Apex Retail Intelligence",
    page_icon="⬡",
    layout="wide",
    initial_sidebar_state="collapsed",
)
st.markdown(design_system.CSS, unsafe_allow_html=True)

# ── Auto-refresh (non-blocking) ────────────────────────────────────────────
if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = time.time()
if "refresh_count" not in st.session_state:
    st.session_state.refresh_count = 0

elapsed = time.time() - st.session_state.last_refresh
if elapsed >= AUTO_REFRESH_SECONDS:
    st.session_state.last_refresh = time.time()
    st.session_state.refresh_count += 1
    st.cache_data.clear()
    st.rerun()

# ── Command Strip — store selector (must run before data fetch) ────────────
_STORES = list(STORE_NAMES.keys())
_LABELS = [STORE_NAMES[s] for s in _STORES]

strip_cols = st.columns([1.8, 1.8, 6, 1.8], gap="small")

with strip_cols[0]:
    st.markdown(
        """
        <div class="cmd-brand" style="padding-left:20px;">
            <div class="cmd-brand-mark">
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none"
                     xmlns="http://www.w3.org/2000/svg">
                  <rect x="1" y="1" width="8" height="8" rx="1.5" fill="#fff" opacity="0.22"/>
                  <rect x="11" y="1" width="8" height="8" rx="1.5" fill="#fff" opacity="0.48"/>
                  <rect x="1" y="11" width="8" height="8" rx="1.5" fill="#fff" opacity="0.72"/>
                  <rect x="11" y="11" width="8" height="8" rx="1.5" fill="#06B6D4"/>
                  <circle cx="15" cy="15" r="2.2" fill="#fff"/>
                </svg>
            </div>
            <div class="cmd-brand-text">
                <div class="cmd-brand-name">Apex Retail</div>
                <div class="cmd-brand-sub">Intelligence</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with strip_cols[1]:
    selected_label = st.selectbox(
        label="Store",
        options=_LABELS,
        key="store_selector",
        label_visibility="collapsed",
    )
    store_id = _STORES[_LABELS.index(selected_label)]

# ── Fetch all data ─────────────────────────────────────────────────────────
with st.spinner(""):
    metrics_data  = fetch(f"/stores/{store_id}/metrics")  or {}
    heatmap_data  = fetch(f"/stores/{store_id}/heatmap")  or {}
    anomaly_data  = fetch(f"/stores/{store_id}/anomalies") or {}
    funnel_data   = fetch(f"/stores/{store_id}/funnel")   or {}
    health_data   = fetch("/health")                       or {}
    store_events  = load_recent_events(store_id)

metrics = metrics_data if metrics_data else {}

# ── Derived signals for command strip ─────────────────────────────────────
visitors  = metrics.get("unique_visitors", 0)
conv      = metrics.get("conversion_rate", 0.0)
aband     = metrics.get("abandonment_rate", 0.0)
dwell_s   = round(metrics.get("avg_dwell_time_ms", 0) / 1000, 0)
depth     = metrics.get("queue_depth", {}).get("current", 0)
store_score = compute_store_score(metrics, anomaly_data)
sc_color, _, sc_label = score_palette(store_score)
top_zn, top_zh, _ = top_zone_data(heatmap_data)
peak_h = peak_traffic_label(store_events)

conv_cls  = "kv-green" if conv >= 0.15 else ("kv-amber" if conv >= 0.08 else "kv-red")
aband_cls = "kv-red" if aband >= 0.4 else ("kv-amber" if aband >= 0.2 else "kv-green")
depth_cls = "kv-red" if depth >= 5 else ("kv-amber" if depth >= 3 else "kv-green")
dwell_cls = "kv-cyan"

kpi_html = f"""
<div class="cmd-kpi-area" style="padding:0 8px;">
    <div class="cmd-kpi-item">
        <div class="cmd-kpi-label">Visitors</div>
        <div class="cmd-kpi-value">{visitors:,}</div>
    </div>
    <div class="cmd-kpi-item">
        <div class="cmd-kpi-label">Conversion</div>
        <div class="cmd-kpi-value {conv_cls}">{conv*100:.1f}%</div>
    </div>
    <div class="cmd-kpi-item">
        <div class="cmd-kpi-label">Abandonment</div>
        <div class="cmd-kpi-value {aband_cls}">{aband*100:.0f}%</div>
    </div>
    <div class="cmd-kpi-item">
        <div class="cmd-kpi-label">Avg Dwell</div>
        <div class="cmd-kpi-value {dwell_cls}">{dwell_s:.0f}s</div>
    </div>
    <div class="cmd-kpi-item">
        <div class="cmd-kpi-label">Queue</div>
        <div class="cmd-kpi-value {depth_cls}">{depth}</div>
    </div>
    <div class="cmd-kpi-item">
        <div class="cmd-kpi-label">Store Score</div>
        <div class="cmd-kpi-value" style="color:{sc_color};">{store_score}</div>
    </div>
    <div class="cmd-kpi-item">
        <div class="cmd-kpi-label">Hot Zone</div>
        <div class="cmd-kpi-value kv-cyan" style="font-size:12px;">
            {_html.escape(top_zn[:12])} {top_zh*100:.0f}%
        </div>
    </div>
</div>
"""
with strip_cols[2]:
    st.markdown(f'<div style="padding:12px 0;">{kpi_html}</div>', unsafe_allow_html=True)

# System health badge
with strip_cols[3]:
    api_status  = health_data.get("status", "error")
    stale       = health_data.get("stale_feed", False)
    uptime_s    = health_data.get("uptime_s", 0)
    uptime_m    = round(uptime_s / 60, 1) if uptime_s else 0

    if api_status == "ok" and not stale:
        pill_class, pill_label = "sys-pill-live", "LIVE"
    elif api_status == "degraded" or stale:
        pill_class, pill_label = "sys-pill-warn", "STALE"
    else:
        pill_class, pill_label = "sys-pill-err", "ERROR"

    n_anomalies = len((anomaly_data or {}).get("anomalies", []))
    anom_label  = f"{n_anomalies} Alert{'s' if n_anomalies != 1 else ''}" if n_anomalies else "0 Alerts"
    anom_class  = "sys-pill-err" if n_anomalies > 0 else "sys-pill-live"
    next_refresh = max(0, int(AUTO_REFRESH_SECONDS - elapsed))

    st.markdown(
        f"""
        <div style="display:flex; flex-direction:column; gap:6px; padding:14px 0 14px 8px;">
            <div class="sys-pill {pill_class}">
                <span class="sys-dot"></span>{_html.escape(pill_label)} · {uptime_m}m
            </div>
            <div class="sys-pill {anom_class}">{_html.escape(anom_label)}</div>
            <div class="refresh-tag">&varr; {next_refresh}s</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ── Divider ────────────────────────────────────────────────────────────────
st.markdown('<hr style="border:none; border-top:1px solid #1E3A5F; margin:0;">', unsafe_allow_html=True)

# ── Alert Banner ───────────────────────────────────────────────────────────
alert = build_alert_state(metrics, anomaly_data)
st.markdown(
    f"""
    <div class="alert-banner {alert['banner_class']}">
        <span class="alert-pill {alert['pill_class']}">{_html.escape(alert['label'])}</span>
        <div class="alert-divider"></div>
        <div class="alert-msg">{alert['message']}</div>
        <div class="alert-cta">{_html.escape(alert['cta'])}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ── Divider ────────────────────────────────────────────────────────────────
st.markdown('<hr style="border:none; border-top:1px solid #1E3A5F; margin:0;">', unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════
# TAB NAVIGATION
# ═══════════════════════════════════════════════════════════════════════════
tab_ops, tab_journey, tab_queue, tab_risk = st.tabs([
    "Operations",
    "Journey Analytics",
    "Queue Intelligence",
    "Risk & Anomalies",
])

# ── Tab 1: Operations ───────────────────────────────────────────────────────
with tab_ops:
    # Revenue Pulse
    st.markdown('<div class="sec-label sec-label-first">Revenue Pulse</div>', unsafe_allow_html=True)
    render_revenue_pulse(metrics, anomaly_data)

    # Floor Intelligence (hero)
    st.markdown('<div class="sec-label">Store Floor Intelligence</div>', unsafe_allow_html=True)
    render_floor_intelligence(heatmap_data)

    # AI Action Center
    st.markdown('<div class="sec-label">AI Decision Center</div>', unsafe_allow_html=True)
    render_ai_action_center(metrics, heatmap_data, anomaly_data, funnel_data)

    # Live Event Feed (collapsible)
    with st.expander(f"Live Operational Feed — {len(store_events)} recent events"):
        if not store_events:
            st.markdown(
                '<div style="color:#4A6080; font-size:12px; padding:8px 0;">'
                'No recent events in the current window.</div>',
                unsafe_allow_html=True,
            )
        else:
            _TYPE_COLORS = {
                "ENTRY":                 ("#10B981", "#10B98118"),
                "EXIT":                  ("#4A6080", "#1E3A5F28"),
                "ZONE_ENTER":            ("#2563EB", "#2563EB18"),
                "ZONE_EXIT":             ("#4A6080", "#1E3A5F28"),
                "ZONE_DWELL":            ("#06B6D4", "#06B6D418"),
                "BILLING_QUEUE_JOIN":    ("#F59E0B", "#F59E0B18"),
                "BILLING_QUEUE_ABANDON": ("#EF4444", "#EF444418"),
                "REENTRY":               ("#8B5CF6", "#8B5CF618"),
            }
            feed_html = ""
            for ev in reversed(store_events[-30:]):
                etype = ev.get("event_type", "")
                tc, bg = _TYPE_COLORS.get(etype, ("#4A6080", "#1E3A5F18"))
                zone   = _html.escape(str(ev.get("zone_id", "—") or "—"))
                ts_raw = ev.get("timestamp", "")
                ts_disp = ts_raw[11:16] if len(ts_raw) >= 16 else "—"
                vid    = _html.escape(str(ev.get("visitor_id", "?"))[:10])
                feed_html += f"""
                <div class="live-feed-item">
                    <span class="live-feed-type"
                          style="color:{tc}; background:{bg}; border:1px solid {tc}33;">
                        {_html.escape(etype.replace('_', ' '))}
                    </span>
                    <span class="live-feed-zone">{zone} &middot; visitor {vid}</span>
                    <span class="live-feed-ts">{_html.escape(ts_disp)}</span>
                </div>
                """
            st.markdown(feed_html, unsafe_allow_html=True)

# ── Tab 2: Journey Analytics ───────────────────────────────────────────────
with tab_journey:
    render_journey_tab(metrics, funnel_data, heatmap_data)

# ── Tab 3: Queue Intelligence ──────────────────────────────────────────────
with tab_queue:
    render_queue_tab(metrics, anomaly_data)

# ── Tab 4: Risk & Anomalies ────────────────────────────────────────────────
with tab_risk:
    render_risk_tab(metrics, anomaly_data)
