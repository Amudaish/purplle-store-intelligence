"""
Risk & Anomaly Tab — composite risk score + ranked anomaly cards.
"""

from __future__ import annotations
import html as _html
import streamlit as st
from data_layer import compute_risk_score, AVG_TICKET_INR

_SEVERITY_CFG = {
    "CRITICAL": {"color": "#EF4444", "bg": "#EF444418", "badge_bg": "#EF444418", "badge_border": "#EF444444"},
    "HIGH":     {"color": "#F59E0B", "bg": "#F59E0B18", "badge_bg": "#F59E0B18", "badge_border": "#F59E0B44"},
    "MEDIUM":   {"color": "#6366F1", "bg": "#6366F118", "badge_bg": "#6366F118", "badge_border": "#6366F144"},
    "LOW":      {"color": "#10B981", "bg": "#10B98118", "badge_bg": "#10B98118", "badge_border": "#10B98144"},
}

_TYPE_LABEL = {
    "QUEUE_SPIKE":         "Queue Depth Spike",
    "BILLING_QUEUE_SPIKE": "Billing Queue Spike",
    "CONVERSION_DROP":     "Conversion Rate Drop",
    "DEAD_ZONE":           "Dead Zone Detected",
    "STALE_FEED":          "Camera Feed Stale",
    "HIGH_DWELL":          "Unusually High Dwell Time",
}


def render_risk_tab(metrics: dict, anomaly_data: dict) -> None:
    anomalies = (anomaly_data or {}).get("anomalies", [])
    _ord      = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    anomalies = sorted(anomalies, key=lambda a: _ord.get(a.get("severity", "LOW"), 4))

    risk_score, risk_color, risk_label = compute_risk_score(metrics, anomaly_data)

    aband    = metrics.get("abandonment_rate", 0.0)
    depth    = metrics.get("queue_depth", {}).get("current", 0)
    conv     = metrics.get("conversion_rate", 0.0)
    visitors = metrics.get("unique_visitors", 0)
    n_crit   = sum(1 for a in anomalies if a.get("severity") == "CRITICAL")
    n_high   = sum(1 for a in anomalies if a.get("severity") == "HIGH")

    from data_layer import BENCHMARK_CONV
    conv_gap = max(0.0, (BENCHMARK_CONV - conv) * 100)

    c1, c2 = st.columns([1, 2], gap="medium")

    # ── Left: Risk Composite ──
    with c1:
        factor_rows = ""
        for name, val in [
            ("Queue Abandonment",   f"{aband*100:.0f}%"),
            ("Queue Depth",         str(depth)),
            ("Conv. vs Benchmark",  f"\u2212{conv_gap:.1f}pp"),
            ("Critical Anomalies",  str(n_crit)),
            ("High Anomalies",      str(n_high)),
        ]:
            factor_rows += (
                '<div class="risk-factor-row">'
                f'<span class="risk-factor-name">{_html.escape(name)}</span>'
                f'<span class="risk-factor-val">{_html.escape(val)}</span>'
                '</div>'
            )

        _risk_html = (
            '<div class="risk-overview">'
            '<div class="risk-overview-header">'
            '<div class="risk-overview-title">Composite Risk Score</div>'
            '</div>'
            '<div class="risk-composite">'
            '<div class="risk-score-wrap">'
            f'<div class="risk-score-big" style="color:{risk_color};">{risk_score}</div>'
            f'<div class="risk-score-lbl" style="color:{risk_color};">{_html.escape(risk_label)}</div>'
            '</div>'
            f'<div class="risk-factors">{factor_rows}</div>'
            '</div>'
            '</div>'
        )
        st.markdown(_risk_html, unsafe_allow_html=True)

    # ── Right: Anomaly Cards ──
    with c2:
        if not anomalies:
            st.markdown(
                '<div class="no-data"><div class="no-data-title">No Anomalies Detected</div>'
                '<div class="no-data-sub">All metrics are within normal operating range.</div></div>',
                unsafe_allow_html=True,
            )
            return

        for anom in anomalies:
            sev       = anom.get("severity", "LOW")
            atype     = anom.get("type", "")
            cfg       = _SEVERITY_CFG.get(sev, _SEVERITY_CFG["LOW"])
            type_lbl  = _html.escape(_TYPE_LABEL.get(atype, atype.replace("_", " ").title()))
            action    = _html.escape(str(anom.get("suggested_action", "")))
            raw_dt    = anom.get("detected_at", "")
            if raw_dt and isinstance(raw_dt, str) and len(raw_dt) >= 16:
                ts_str = _html.escape(raw_dt[:16].replace("T", " ") + " UTC")
            else:
                ts_str = _html.escape(str(raw_dt) if raw_dt else "N/A")
            sev_safe = _html.escape(str(sev))

            st.markdown(
                f"""
                <div class="anom-card">
                    <div class="anom-accent" style="background:{cfg['color']};"></div>
                    <div class="anom-body">
                        <div class="anom-type">{type_lbl}</div>
                        <div class="anom-action">{action}</div>
                        <div class="anom-ts">Detected: {ts_str}</div>
                    </div>
                    <div class="anom-badge-wrap">
                        <span class="anom-badge"
                              style="color:{cfg['color']}; background:{cfg['badge_bg']};
                                     border:1px solid {cfg['badge_border']};">
                            {sev_safe}
                        </span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
