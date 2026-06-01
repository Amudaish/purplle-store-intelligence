"""
Queue Intelligence Tab — queue depth ring, abandonment bar, staffing directive.
"""

from __future__ import annotations
import html as _html
import streamlit as st
from data_layer import AVG_TICKET_INR, staffing_recommendation


def render_queue_tab(metrics: dict, anomaly_data: dict) -> None:
    depth     = metrics.get("queue_depth", {}).get("current", 0)
    avg_depth = metrics.get("queue_depth", {}).get("avg", 0.0)
    max_depth = metrics.get("queue_depth", {}).get("max", 0)
    aband     = metrics.get("abandonment_rate", 0.0)
    visitors  = metrics.get("unique_visitors", 0)
    conv      = metrics.get("conversion_rate", 0.0)

    # Risk classification
    if depth >= 5 or aband >= 0.4:
        q_color = "#EF4444"; q_label = "CRITICAL"
    elif depth >= 3 or aband >= 0.2:
        q_color = "#F59E0B"; q_label = "ELEVATED"
    else:
        q_color = "#10B981"; q_label = "NOMINAL"

    aband_pct  = aband * 100
    lost_amt   = int(visitors * aband * AVG_TICKET_INR)
    lost_str   = f"₹{lost_amt:,}" if lost_amt < 1_00_000 else f"₹{lost_amt/1_00_000:.1f}L"

    staff_lbl, staff_color, staff_rationale = staffing_recommendation(metrics, anomaly_data)

    c1, c2 = st.columns([1, 2], gap="medium")

    # ── Left: Queue Depth Ring ──
    with c1:
        ring_border = q_color
        st.markdown(
            f"""
            <div class="queue-panel">
                <div style="font-size:9px; font-weight:800; letter-spacing:0.18em;
                            text-transform:uppercase; color:#4A6080; margin-bottom:12px;">
                    LIVE QUEUE STATUS
                </div>
                <div class="q-ring" style="border-color:{ring_border}33;
                                            box-shadow:0 0 24px {ring_border}18;">
                    <div class="q-depth-val" style="color:{q_color};">{depth}</div>
                    <div class="q-depth-lbl">in queue</div>
                </div>
                <div class="q-state-label" style="color:{q_color};">{_html.escape(q_label)}</div>
                <div class="q-desc">
                    Avg depth {avg_depth:.1f} &middot; Peak {max_depth} today
                </div>
                <div class="q-aband-row">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <span class="q-aband-lbl">Abandonment Rate</span>
                        <span class="q-aband-pct" style="color:{q_color};">{aband_pct:.0f}%</span>
                    </div>
                    <div class="q-aband-track">
                        <div class="q-aband-fill"
                             style="width:{min(aband_pct,100):.0f}%; background:{q_color};"></div>
                    </div>
                </div>
                <div style="font-size:12px; color:#4A6080; line-height:1.4; margin-top:4px; text-align:center;">
                    Revenue at risk: <span style="color:{q_color}; font-weight:700;">{_html.escape(lost_str)}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # ── Right: Staffing Directive + Context ──
    with c2:
        n_anom = len((anomaly_data or {}).get("anomalies", []))
        st.markdown(
            f"""
            <div class="staff-panel">
                <div class="staff-panel-header">
                    <div class="staff-panel-title">Staffing Directive</div>
                </div>
                <div class="staff-body">
                    <div class="staff-directive" style="color:{staff_color};">
                        {_html.escape(staff_lbl)}
                    </div>
                    <div class="staff-rationale">{_html.escape(staff_rationale)}</div>
                    <div class="staff-metric-row">
                        <div class="staff-metric">
                            <div class="staff-metric-val" style="color:{q_color};">{depth}</div>
                            <div class="staff-metric-lbl">Queue Depth</div>
                        </div>
                        <div class="staff-metric">
                            <div class="staff-metric-val" style="color:{q_color};">{aband_pct:.0f}%</div>
                            <div class="staff-metric-lbl">Abandonment</div>
                        </div>
                        <div class="staff-metric">
                            <div class="staff-metric-val" style="color:#F59E0B;">{n_anom}</div>
                            <div class="staff-metric-lbl">Active Anomalies</div>
                        </div>
                        <div class="staff-metric">
                            <div class="staff-metric-val" style="color:#EF4444;">{_html.escape(lost_str)}</div>
                            <div class="staff-metric-lbl">Revenue at Risk</div>
                        </div>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
