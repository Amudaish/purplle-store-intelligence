"""
Anomaly Panel component — displays anomaly alerts with severity styling.
"""

from __future__ import annotations

import html as _html

import streamlit as st

_SEVERITY_CONFIG = {
    "CRITICAL": {"bg": "#1e293b", "border": "#ef4444", "text": "#fca5a5", "badge_bg": "#ef444422", "badge_tc": "#ef4444"},
    "HIGH":     {"bg": "#1e293b", "border": "#f97316", "text": "#fdba74", "badge_bg": "#f9731622", "badge_tc": "#f97316"},
    "MEDIUM":   {"bg": "#1e293b", "border": "#eab308", "text": "#fde047", "badge_bg": "#eab30822", "badge_tc": "#eab308"},
    "LOW":      {"bg": "#1e293b", "border": "#3b82f6", "text": "#93c5fd", "badge_bg": "#3b82f622", "badge_tc": "#3b82f6"},
}

_TYPE_LABEL = {
    "QUEUE_SPIKE":      "Queue Depth Alert",
    "CONVERSION_DROP":  "Conversion Drop",
    "DEAD_ZONE":        "Dead Zone Detected",
}


def render_anomaly_panel(anomaly_data: dict) -> None:
    """
    Render anomaly alerts sorted by severity.

    Parameters
    ----------
    anomaly_data : dict — response from GET /stores/{id}/anomalies
    """
    anomalies = anomaly_data.get("anomalies", [])

    if not anomalies:
        st.success("✅ No anomalies detected")
        return

    severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    anomalies = sorted(anomalies, key=lambda a: severity_order.get(a["severity"], 4))

    for anomaly in anomalies:
        cfg = _SEVERITY_CONFIG.get(anomaly["severity"], _SEVERITY_CONFIG["LOW"])
        type_label = _TYPE_LABEL.get(anomaly["type"], anomaly["type"])

        # Escape dynamic DB values before injecting into HTML
        safe_type_label    = _html.escape(str(type_label))
        safe_action        = _html.escape(str(anomaly.get('suggested_action', '')))
        raw_detected       = anomaly.get('detected_at', '')
        # Format datetime if it looks like ISO string; show only YYYY-MM-DD HH:MM UTC
        if raw_detected and isinstance(raw_detected, str) and len(raw_detected) >= 16:
            safe_detected = _html.escape(raw_detected[:16].replace('T', ' ') + ' UTC')
        else:
            safe_detected = _html.escape(str(raw_detected) if raw_detected else 'N/A')

        with st.container():
            st.markdown(
                f"""
                <div style="
                    background: {cfg['bg']};
                    border-left: 3px solid {cfg['border']};
                    border-radius: 4px;
                    padding: 16px;
                    margin-bottom: 8px;
                    border-top: 1px solid #334155;
                    border-right: 1px solid #334155;
                    border-bottom: 1px solid #334155;
                ">
                    <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                        <div>
                            <div style="font-size:14px; font-weight:600; color:#f8fafc; letter-spacing:-0.01em;">
                                {safe_type_label}
                            </div>
                            <div style="color:#94a3b8; font-size:13px; margin-top:4px; line-height:1.4;">
                                {safe_action}
                            </div>
                        </div>
                        <span style="font-size:11px; font-weight:600; background:{cfg['badge_bg']}; color:{cfg['badge_tc']}; padding:2px 8px; border-radius:4px; margin-left:12px;">
                            {_html.escape(str(anomaly['severity']))}
                        </span>
                    </div>
                    <div style="color:#64748b; font-size:11px; margin-top:12px;">
                        Detected: {safe_detected}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
