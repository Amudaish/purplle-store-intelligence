"""
Funnel Chart component — renders a Plotly funnel visualisation.
"""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st


def render_funnel_chart(funnel_data: dict) -> None:
    """
    Render an interactive Plotly funnel chart from GET /stores/{id}/funnel data.

    Parameters
    ----------
    funnel_data : dict — response from GET /stores/{id}/funnel
    """
    funnel     = funnel_data.get("funnel", [])
    reentries  = funnel_data.get("reentry_sessions", 0)

    if not funnel:
        st.info("No funnel data available yet.")
        return

    stages = [s["stage"].replace("_", " ") for s in funnel]
    counts = [s["count"] for s in funnel]
    pcts   = [s["pct"] for s in funnel]

    # Custom hover text
    text = [f"{c:,}  ·  {p:.1f}%" for c, p in zip(counts, pcts)]

    # Gradient palette: indigo → violet → emerald → teal
    colors = ["#4F46E5", "#7C3AED", "#0D9488", "#10B981"]
    if len(funnel) > 4:
        colors = ["#4F46E5", "#6D28D9", "#7C3AED", "#0D9488", "#10B981"][: len(funnel)]

    fig = go.Figure(
        go.Funnel(
            y=stages,
            x=counts,
            text=text,
            textinfo="text",
            textfont={"size": 13, "color": "#f8fafc", "family": "Inter"},
            marker={
                "color": colors[: len(stages)],
                "line": {"width": 0},
            },
            connector={"line": {"color": "#334155", "width": 2, "dash": "dot"}},
            hovertemplate="<b>%{y}</b><br>Visitors: %{x:,}<extra></extra>",
        )
    )

    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"color": "#94a3b8", "family": "Inter"},
        height=320,
        margin={"l": 20, "r": 20, "t": 20, "b": 20},
        funnelmode="stack",
    )

    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    if reentries > 0:
        st.markdown(
            f'<div style="text-align:center; font-size:12px; font-weight:500; color:#8b5cf6; margin-top:-8px;">'
            f'🔄 {reentries} re-entry session(s) detected</div>',
            unsafe_allow_html=True,
        )
