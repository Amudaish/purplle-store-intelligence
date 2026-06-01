"""
Sankey Visitor Flow — Enterprise Hero Feature.

Renders a dynamic, fully balanced Sankey diagram synthesizing 
funnel conversion data and heatmap zone analytics to visualize 
the complete customer journey from entry to purchase or abandonment.
"""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st


def render_sankey_flow(metrics: dict, funnel_data: dict, heatmap_data: dict) -> None:
    """
    Render a balanced Sankey diagram using Plotly.

    Parameters
    ----------
    metrics : dict
    funnel_data : dict — response from GET /stores/{id}/funnel
    heatmap_data : dict — response from GET /stores/{id}/heatmap
    """
    funnel_data  = funnel_data  or {}
    heatmap_data = heatmap_data or {}

    funnel = funnel_data.get("funnel", [])
    zones  = heatmap_data.get("zones", [])

    if not funnel or not zones:
        st.info("Insufficient data to render visitor flow.")
        return

    # Extract funnel stage counts
    # Expected stages: Entry, Zone Visit, Billing Queue, Purchase
    counts = {s["stage"]: s["count"] for s in funnel}
    
    total_entry = counts.get("Entry", 0)
    total_zone = counts.get("Zone Visit", 0)
    total_billing = counts.get("Billing Queue", 0)
    total_purchase = counts.get("Purchase", 0)

    if total_entry == 0:
        st.info("No visitors recorded in the current time window.")
        return

    # Calculate Drop-offs
    entry_dropoff = max(0, total_entry - total_zone)
    zone_dropoff = max(0, total_zone - total_billing)
    billing_dropoff = max(0, total_billing - total_purchase)

    # Normalize heatmap zone visits to perfectly distribute the `total_zone` count
    raw_zone_visits = [z.get("visits", 0) for z in zones]
    total_raw_visits = sum(raw_zone_visits) or 1
    
    # Node Definitions
    # 0: Store Entry
    # 1: Walk-outs (Entry Drop-off)
    # 2: Billing Queue
    # 3: Purchase (Checkout)
    # 4: Mid-journey Abandonment
    # 5: Queue Abandonment
    # 6...: Individual Zones

    labels = [
        "Store Entry",          # 0
        "Walk-outs",            # 1
        "Billing Queue",        # 2
        "Purchase",             # 3
        "Browsing Abandonment", # 4
        "Queue Abandonment"     # 5
    ]

    colors = [
        "#94a3b8", # 0: Entry (Slate)
        "#ef4444", # 1: Walk-outs (Red)
        "#f59e0b", # 2: Billing (Amber)
        "#10b981", # 3: Purchase (Emerald)
        "#ef4444", # 4: Browsing Drop (Red)
        "#ef4444", # 5: Queue Drop (Red)
    ]

    # Append Zone Nodes
    zone_start_idx = len(labels)
    for i, z in enumerate(zones):
        zone_name = z["zone_id"].replace("_", " ").title()
        labels.append(zone_name)
        colors.append("#3b82f6") # Zones (Blue)

    source = []
    target = []
    value = []
    link_colors = []

    def add_link(s: int, t: int, v: float, color: str = "rgba(148, 163, 184, 0.2)"):
        if v > 0:
            source.append(s)
            target.append(t)
            value.append(v)
            link_colors.append(color)

    # 1. Entry to Walk-outs
    add_link(0, 1, entry_dropoff, "rgba(239, 68, 68, 0.25)")

    # 2. Entry to Zones
    # 3. Zones to Billing
    # 4. Zones to Browsing Abandonment
    for i, z in enumerate(zones):
        node_id = zone_start_idx + i
        proportion = raw_zone_visits[i] / total_raw_visits
        
        flow_to_zone = total_zone * proportion
        flow_to_billing = total_billing * proportion
        flow_to_abandon = zone_dropoff * proportion

        # Entry -> Zone
        add_link(0, node_id, flow_to_zone, "rgba(59, 130, 246, 0.2)")
        
        # Zone -> Billing
        add_link(node_id, 2, flow_to_billing, "rgba(245, 158, 11, 0.2)")
        
        # Zone -> Browsing Abandonment
        add_link(node_id, 4, flow_to_abandon, "rgba(239, 68, 68, 0.2)")

    # 5. Billing to Purchase
    add_link(2, 3, total_purchase, "rgba(16, 185, 129, 0.3)")

    # 6. Billing to Queue Abandonment
    add_link(2, 5, billing_dropoff, "rgba(239, 68, 68, 0.3)")


    fig = go.Figure(data=[go.Sankey(
        node=dict(
            pad=24,
            thickness=16,
            line=dict(color="#1e293b", width=1),
            label=labels,
            color=colors,
            hovertemplate="%{label}<br>Count: %{value:,.0f}<extra></extra>",
        ),
        link=dict(
            source=source,
            target=target,
            value=value,
            color=link_colors,
            hovertemplate="Flow: %{source.label} → %{target.label}<br>Visitors: %{value:,.0f}<extra></extra>",
        )
    )])

    fig.update_layout(
        title_text="",
        font=dict(size=12, color="#f8fafc", family="Inter"),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=480,
        margin=dict(l=16, r=16, t=24, b=16)
    )

    st.markdown(
        '<div style="font-size:14px; font-weight:600; color:#f8fafc;'
        ' margin-bottom:12px; letter-spacing:0.02em;">Sankey Visitor Flow  · End-to-End Journey</div>',
        unsafe_allow_html=True,
    )
    
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    # Summary metrics below the chart
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(
            f"""
            <div style="background:#1e293b; padding:12px; border-radius:6px; border-left:3px solid #3b82f6;">
                <div style="font-size:11px; color:#94a3b8; font-weight:500;">Store Entries</div>
                <div style="font-size:18px; color:#f8fafc; font-weight:600;">{total_entry:,}</div>
            </div>
            """, unsafe_allow_html=True
        )
    with c2:
        walkout_pct = (entry_dropoff / total_entry * 100) if total_entry else 0
        st.markdown(
            f"""
            <div style="background:#1e293b; padding:12px; border-radius:6px; border-left:3px solid #ef4444;">
                <div style="font-size:11px; color:#94a3b8; font-weight:500;">Walk-out Rate</div>
                <div style="font-size:18px; color:#f8fafc; font-weight:600;">{walkout_pct:.1f}%</div>
            </div>
            """, unsafe_allow_html=True
        )
    with c3:
        queue_aband_pct = (billing_dropoff / total_billing * 100) if total_billing else 0
        st.markdown(
            f"""
            <div style="background:#1e293b; padding:12px; border-radius:6px; border-left:3px solid #f59e0b;">
                <div style="font-size:11px; color:#94a3b8; font-weight:500;">Queue Abandonment</div>
                <div style="font-size:18px; color:#f8fafc; font-weight:600;">{queue_aband_pct:.1f}%</div>
            </div>
            """, unsafe_allow_html=True
        )
    with c4:
        conv_pct = (total_purchase / total_entry * 100) if total_entry else 0
        st.markdown(
            f"""
            <div style="background:#1e293b; padding:12px; border-radius:6px; border-left:3px solid #10b981;">
                <div style="font-size:11px; color:#94a3b8; font-weight:500;">Net Conversion</div>
                <div style="font-size:18px; color:#f8fafc; font-weight:600;">{conv_pct:.1f}%</div>
            </div>
            """, unsafe_allow_html=True
        )
