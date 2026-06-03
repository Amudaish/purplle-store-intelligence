"""
AI Action Center — ranked executive decision cards.
Each card: signal type, urgency, recommendation, impact, confidence, outcome.
"""

from __future__ import annotations
import html as _html
import streamlit as st
from data_layer import generate_executive_actions

_URGENCY_COLORS = {
    "CRITICAL": ("#EF4444", "#EF444418", "#EF444440"),
    "HIGH":     ("#F59E0B", "#F59E0B18", "#F59E0B40"),
    "MEDIUM":   ("#6366F1", "#6366F118", "#6366F140"),
    "LOW":      ("#10B981", "#10B98118", "#10B98140"),
    "STATUS":   ("#10B981", "#10B98118", "#10B98140"),
}

_SIGNAL_COLORS = {
    "QUEUE":      ("#EF4444", "#EF444418"),
    "CONVERSION": ("#F59E0B", "#F59E0B18"),
    "ZONE":       ("#06B6D4", "#06B6D418"),
    "FUNNEL":     ("#8B5CF6", "#8B5CF618"),
    "JOURNEY":    ("#10B981", "#10B98118"),
    "STATUS":     ("#10B981", "#10B98118"),
}


def render_ai_action_center(
    metrics: dict,
    heatmap_data: dict,
    anomaly_data: dict,
    funnel_data: dict,
) -> None:
    actions = generate_executive_actions(metrics, heatmap_data, anomaly_data, funnel_data)

    # Render top 2 side-by-side, then rest below
    if not actions:
        st.markdown(
            '<div class="no-data"><div class="no-data-title">No Actions Generated</div>'
            '<div class="no-data-sub">Insufficient data to produce recommendations.</div></div>',
            unsafe_allow_html=True,
        )
        return

    if len(actions) >= 2:
        c1, c2 = st.columns(2, gap="medium")
        with c1:
            _render_action_card(actions[0], priority=1)
        with c2:
            _render_action_card(actions[1], priority=2)
        for i, action in enumerate(actions[2:], start=3):
            _render_action_card(action, priority=i)
    else:
        _render_action_card(actions[0], priority=1)


def _render_action_card(action: dict, priority: int) -> None:
    signal  = action.get("signal", "STATUS")
    urgency = action.get("urgency", "LOW")

    urg_color, urg_bg, urg_border = _URGENCY_COLORS.get(urgency, _URGENCY_COLORS["LOW"])
    sig_color, sig_bg             = _SIGNAL_COLORS.get(signal, _SIGNAL_COLORS["STATUS"])
    conf     = action.get("confidence_pct", 80)
    impact   = _html.escape(action.get("impact_str", "—"))
    rec      = _html.escape(action.get("recommendation", ""))
    ctx      = _html.escape(action.get("context", ""))
    outcome  = _html.escape(action.get("expected_outcome", "—"))
    action_color = action.get("color", "#2563EB")

    st.markdown(
        f"""
        <div class="ai-card">
            <div class="ai-card-top">
                <span class="ai-priority-num">PRIORITY #{priority}</span>
                <span class="ai-signal-chip"
                      style="color:{sig_color}; background:{sig_bg};
                             border:1px solid {sig_color}33;">{_html.escape(signal)}</span>
                <span class="ai-urgency-chip"
                      style="color:{urg_color}; background:{urg_bg};
                             border:1px solid {urg_border};">{_html.escape(urgency)}</span>
                <div class="ai-conf-area">
                    <div class="ai-conf-label">CONFIDENCE</div>
                    <div class="ai-conf-val">{conf}%</div>
                </div>
            </div>
            <div class="ai-card-body">
                <div class="ai-recommendation" style="color:{action_color};">{rec}</div>
                <div class="ai-context">{ctx}</div>
                <div class="ai-metrics-row">
                    <div class="ai-metric-block">
                        <div class="ai-metric-lbl">Revenue Impact</div>
                        <div class="ai-metric-val" style="color:{action_color};">{impact}</div>
                    </div>
                    <div class="ai-metric-block">
                        <div class="ai-metric-lbl">Confidence</div>
                        <div class="ai-metric-val" style="color:#06B6D4;">{conf}%</div>
                    </div>
                </div>
            </div>
            <div class="ai-card-footer">
                <div class="ai-outcome">
                    Expected: <strong>{outcome}</strong>
                </div>
                <div class="ai-act">ACT NOW &rarr;</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
