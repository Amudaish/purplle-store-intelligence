"""
Journey Tab — Sankey visitor flow + funnel stats.
Full-width hero chart with stage breakdown strip.
"""

from __future__ import annotations
import html as _html
import streamlit as st
import plotly.graph_objects as go


def render_journey_tab(metrics: dict, funnel_data: dict, heatmap_data: dict) -> None:
    funnel_data  = funnel_data  or {}
    heatmap_data = heatmap_data or {}

    funnel = funnel_data.get("funnel", [])
    zones  = heatmap_data.get("zones", [])

    if not funnel or not zones:
        st.markdown(
            '<div class="no-data"><div class="no-data-title">Journey Data Unavailable</div>'
            '<div class="no-data-sub">Funnel or zone data has not been received yet. '
            'The pipeline may still be warming up.</div></div>',
            unsafe_allow_html=True,
        )
        return

    counts = {s["stage"]: s["count"] for s in funnel}
    total_entry    = counts.get("Entry", 0)
    total_zone     = counts.get("Zone Visit", 0)
    total_billing  = counts.get("Billing Queue", 0)
    total_purchase = counts.get("Purchase", 0)

    if total_entry == 0:
        st.info("No visitor entries recorded in the current window.")
        return

    entry_drop   = max(0, total_entry - total_zone)
    zone_drop    = max(0, total_zone - total_billing)
    billing_drop = max(0, total_billing - total_purchase)

    raw_visits    = [z.get("visits", 0) for z in zones]
    total_raw     = sum(raw_visits) or 1

    # Build Sankey nodes
    labels = ["Store Entry", "Walk-outs", "Billing Queue", "Purchase", "Browsing Exit", "Queue Abandon"]
    colors = ["#94A3B8", "#EF4444", "#F59E0B", "#10B981", "#EF4444", "#EF4444"]
    zone_start = len(labels)
    for z in zones:
        labels.append(z["zone_id"].replace("_", " ").title())
        colors.append("#3B82F6")

    source, target, value, link_colors = [], [], [], []

    def add_link(s, t, v, c="rgba(148,163,184,0.18)"):
        if v > 0:
            source.append(s); target.append(t)
            value.append(v); link_colors.append(c)

    add_link(0, 1, entry_drop, "rgba(239,68,68,0.22)")

    for i, z in enumerate(zones):
        nid  = zone_start + i
        prop = raw_visits[i] / total_raw
        add_link(0, nid, total_zone * prop, "rgba(59,130,246,0.18)")
        add_link(nid, 2, total_billing * prop, "rgba(245,158,11,0.18)")
        add_link(nid, 4, zone_drop * prop, "rgba(239,68,68,0.18)")

    add_link(2, 3, total_purchase, "rgba(16,185,129,0.28)")
    add_link(2, 5, billing_drop,   "rgba(239,68,68,0.28)")

    fig = go.Figure(data=[go.Sankey(
        node=dict(
            pad=20, thickness=14,
            line=dict(color="#060B14", width=0.5),
            label=labels, color=colors,
            hovertemplate="%{label}<br>Visitors: %{value:,.0f}<extra></extra>",
        ),
        link=dict(
            source=source, target=target, value=value, color=link_colors,
            hovertemplate="Flow: %{source.label} &rarr; %{target.label}<br>Visitors: %{value:,.0f}<extra></extra>",
        ),
    )])
    fig.update_layout(
        font=dict(size=11, color="#8AA0C0", family="Inter"),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=460,
        margin=dict(l=16, r=16, t=16, b=16),
    )

    # Compute stats
    walkout_pct  = entry_drop / total_entry * 100 if total_entry else 0
    q_aband_pct  = billing_drop / total_billing * 100 if total_billing else 0
    conv_pct     = total_purchase / total_entry * 100 if total_entry else 0
    reentries    = funnel_data.get("reentry_sessions", 0)

    walkout_c = "#EF4444" if walkout_pct > 30 else ("#F59E0B" if walkout_pct > 15 else "#10B981")
    q_c       = "#EF4444" if q_aband_pct > 40 else ("#F59E0B" if q_aband_pct > 20 else "#10B981")
    conv_c    = "#10B981" if conv_pct >= 15 else ("#F59E0B" if conv_pct >= 8 else "#EF4444")
    re_c      = "#06B6D4" if reentries > 5 else "#4A6080"

    st.markdown(
        f"""
        <div class="journey-wrap">
            <div class="journey-header">
                <span class="journey-header-title">Visitor Journey Flow &middot; End-to-End Conversion</span>
                <span style="font-size:10px; color:#4A6080; font-weight:600;">
                    {total_entry:,} entries &middot; {total_purchase:,} purchases
                </span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    st.markdown(
        f"""
        <div class="journey-wrap" style="margin-top:-4px;">
            <div class="journey-stat-strip">
                <div class="journey-stat">
                    <div class="journey-stat-lbl">Store Entries</div>
                    <div class="journey-stat-val" style="color:#F0F6FF;">{total_entry:,}</div>
                </div>
                <div class="journey-stat">
                    <div class="journey-stat-lbl">Walk-out Rate</div>
                    <div class="journey-stat-val" style="color:{walkout_c};">{walkout_pct:.1f}%</div>
                </div>
                <div class="journey-stat">
                    <div class="journey-stat-lbl">Queue Abandon</div>
                    <div class="journey-stat-val" style="color:{q_c};">{q_aband_pct:.1f}%</div>
                </div>
                <div class="journey-stat">
                    <div class="journey-stat-lbl">Net Conversion</div>
                    <div class="journey-stat-val" style="color:{conv_c};">{conv_pct:.1f}%</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if reentries > 0:
        st.markdown(
            f'<div style="margin-top:10px; font-size:12px; color:{re_c}; font-weight:600; text-align:center;">'
            f'&#x21BA; {reentries} re-entry session(s) detected &mdash; high purchase-intent signal</div>',
            unsafe_allow_html=True,
        )
