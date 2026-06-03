"""
Heatmap View — Enterprise Zone Intelligence.

Renders a visual store floor plan (Plotly SVG layout) alongside
a precision zone analytics table. Heat scores drive both color
intensity and glow effects.
"""

from __future__ import annotations

import html as _html

import plotly.graph_objects as go
import streamlit as st


# ── Static zone grid layout  (zone_id → grid position) ──────────────────────
# Positions are in a normalised coordinate system (0–1).
# Unknown zones fall into an auto-layout grid.
_ZONE_GRID: dict[str, dict] = {
    "entrance":  {"col": 1, "row": 2, "label": "Entrance"},
    "haircare":  {"col": 0, "row": 0, "label": "Haircare"},
    "skincare":  {"col": 1, "row": 0, "label": "Skincare"},
    "fragrance": {"col": 0, "row": 1, "label": "Fragrance"},
    "billing":   {"col": 2, "row": 1, "label": "Billing"},
    "checkout":  {"col": 2, "row": 1, "label": "Checkout"},
    "cosmetics": {"col": 2, "row": 0, "label": "Cosmetics"},
    "wellness":  {"col": 0, "row": 2, "label": "Wellness"},
}

# Heat → visual palette
def _heat_palette(heat: float) -> tuple[str, str, str, float]:
    """(fill_rgba, border_hex, glow_rgba, opacity)"""
    if heat >= 0.85:
        return "rgba(6,182,212,0.20)", "#06B6D4", "rgba(6,182,212,0.35)", 1.0
    if heat >= 0.65:
        return "rgba(79,70,229,0.20)", "#4F46E5", "rgba(79,70,229,0.30)", 0.9
    if heat >= 0.40:
        return "rgba(124,58,237,0.18)", "#7C3AED", "rgba(124,58,237,0.25)", 0.8
    if heat >= 0.20:
        return "rgba(71,85,105,0.25)", "#475569", "rgba(71,85,105,0.15)", 0.7
    return "rgba(14,26,46,0.60)", "#132040", "rgba(14,26,46,0.10)", 0.5


def _build_floor_plan(zones: list) -> go.Figure:
    """Build an SVG-style store floor plan using Plotly shapes."""

    CELL_W   = 1.4   # cell width
    CELL_H   = 1.0   # cell height
    GAP      = 0.08  # gap between cells

    # Assign grid positions
    positioned: list[dict] = []
    auto_col, auto_row = 0, 3  # auto-layout fallback below grid
    cols_used = set()

    for zone in zones:
        zid   = zone["zone_id"].lower()
        heat  = zone.get("heat_score", 0.0)
        label = zone.get("zone_id", "").replace("_", " ").title()

        if zid in _ZONE_GRID:
            g = _ZONE_GRID[zid]
            col, row = g["col"], g["row"]
            label = g["label"]
        else:
            col, row = auto_col, auto_row
            auto_col += 1

        cols_used.add(col)
        positioned.append({
            "col": col, "row": row,
            "label": label,
            "heat": heat,
            "visits": zone.get("visits", 0),
            "avg_dwell_s": round(zone.get("avg_dwell_ms", 0) / 1000, 1),
            "confidence": zone.get("data_confidence") or "OK",
        })

    max_col = max((p["col"] for p in positioned), default=2)
    max_row = max((p["row"] for p in positioned), default=1)

    total_w = (max_col + 1) * (CELL_W + GAP)
    total_h = (max_row + 1) * (CELL_H + GAP)

    fig = go.Figure()

    # Background grid lines (subtle)
    for c in range(max_col + 2):
        x = c * (CELL_W + GAP) - GAP / 2
        fig.add_shape(type="line",
            x0=x, y0=0, x1=x, y1=total_h,
            line=dict(color="rgba(19,32,64,0.4)", width=1, dash="dot"))
    for r in range(max_row + 2):
        y = r * (CELL_H + GAP) - GAP / 2
        fig.add_shape(type="line",
            x0=0, y0=y, x1=total_w, y1=y,
            line=dict(color="rgba(19,32,64,0.4)", width=1, dash="dot"))

    for p in positioned:
        col, row = p["col"], p["row"]
        x0 = col * (CELL_W + GAP)
        x1 = x0 + CELL_W
        # Flip row so row=0 is at the top
        y0 = (max_row - row) * (CELL_H + GAP)
        y1 = y0 + CELL_H

        fill, border, glow, opacity = _heat_palette(p["heat"])

        # Outer glow (hot zones only)
        if p["heat"] >= 0.65:
            fig.add_shape(type="rect",
                x0=x0 - 0.04, y0=y0 - 0.04, x1=x1 + 0.04, y1=y1 + 0.04,
                fillcolor=glow, line=dict(width=0), opacity=0.4)

        # Zone rectangle
        fig.add_shape(type="rect",
            x0=x0, y0=y0, x1=x1, y1=y1,
            fillcolor=fill,
            line=dict(color=border, width=1.5),
            opacity=opacity)

        cx = (x0 + x1) / 2
        cy = (y0 + y1) / 2

        # Zone name
        fig.add_annotation(
            x=cx, y=cy + 0.16,
            text=f"<b>{p['label'].upper()}</b>",
            showarrow=False,
            font=dict(size=12, color="#C8DCFF", family="Inter"),
            xanchor="center", yanchor="middle",
        )

        # Visit count + heat
        heat_pct = f"{p['heat']*100:.0f}%"
        fig.add_annotation(
            x=cx, y=cy - 0.08,
            text=f"{p['visits']:,} visits",
            showarrow=False,
            font=dict(size=10, color=border, family="Inter"),
            xanchor="center", yanchor="middle",
        )
        fig.add_annotation(
            x=cx, y=cy - 0.26,
            text=f"Heat {heat_pct}  ·  {p['avg_dwell_s']}s dwell",
            showarrow=False,
            font=dict(size=9, color="rgba(74,96,128,0.9)", family="Inter"),
            xanchor="center", yanchor="middle",
        )

        # LOW confidence badge
        if p["confidence"] == "LOW":
            fig.add_annotation(
                x=x1 - 0.05, y=y1 - 0.08,
                text="LOW DATA",
                showarrow=False,
                font=dict(size=8, color="#F87171", family="Inter"),
                xanchor="right", yanchor="top",
                bgcolor="rgba(59,10,10,0.8)",
                borderpad=3,
            )

    # Entrance arrow
    cx = total_w / 2
    fig.add_annotation(
        x=cx, y=-0.18,
        text="▲  STORE ENTRANCE",
        showarrow=False,
        font=dict(size=10, color="#2E4870", family="Inter"),
        xanchor="center",
    )
    # Entrance line
    fig.add_shape(type="line",
        x0=cx - 0.4, y0=-0.06, x1=cx + 0.4, y1=-0.06,
        line=dict(color="#132040", width=2))

    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(visible=False, range=[-0.15, total_w + 0.15]),
        yaxis=dict(visible=False, range=[-0.4, total_h + 0.15], scaleanchor="x", scaleratio=1),
        height=max(380, (max_row + 1) * 160 + 80),
        margin=dict(l=0, r=0, t=8, b=20),
    )
    return fig


def render_heatmap_view(heatmap_data: dict) -> None:
    """
    Render the full Zone Intelligence section:
    - Left: Visual store floor plan
    - Right: Zone analytics table with heat bars
    """
    zones = heatmap_data.get("zones", [])
    if not zones:
        st.info("No zone data available yet.")
        return

    col_map, col_table = st.columns([2, 1], gap="large")

    with col_map:
        st.markdown(
            '<div style="font-size:12px; font-weight:600; color:#64748b;'
            ' margin-bottom:12px; letter-spacing:0.04em;">Store Floor Plan  · Live Heat</div>',
            unsafe_allow_html=True,
        )

        # Legend
        st.markdown(
            """
            <div style="display:flex; gap:16px; margin-bottom:8px; flex-wrap:wrap;">
                <span style="font-size:10px; color:#06B6D4; font-weight:600; letter-spacing:0.06em;">
                    ■ HOT ≥85%
                </span>
                <span style="font-size:10px; color:#4F46E5; font-weight:600; letter-spacing:0.06em;">
                    ■ WARM 65–84%
                </span>
                <span style="font-size:10px; color:#7C3AED; font-weight:600; letter-spacing:0.06em;">
                    ■ ACTIVE 40–64%
                </span>
                <span style="font-size:10px; color:#475569; font-weight:600; letter-spacing:0.06em;">
                    ■ COOL 20–39%
                </span>
                <span style="font-size:10px; color:#132040; font-weight:600; letter-spacing:0.06em;">
                    ■ COLD &lt;20%
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        floor_fig = _build_floor_plan(zones)
        st.plotly_chart(floor_fig, use_container_width=True, config={"displayModeBar": False})

    with col_table:
        st.markdown(
            '<div style="font-size:12px; font-weight:600; color:#64748b;'
            ' margin-bottom:12px; letter-spacing:0.04em;">Zone Analytics</div>',
            unsafe_allow_html=True,
        )

        rows_html = ""
        for z in zones:
            heat      = z.get("heat_score", 0.0)
            visits    = z.get("visits", 0)
            dwell_s   = round(z.get("avg_dwell_ms", 0) / 1000, 1)
            zone_label = z["zone_id"].replace("_", " ").title()
            conf      = z.get("data_confidence") or "OK"

            fill, border, _, _ = _heat_palette(heat)
            bar_pct   = int(heat * 100)

            conf_bg = "#ef444422" if conf == "LOW" else "#10b98122"
            conf_tc = "#ef4444" if conf == "LOW" else "#10b981"

            # Trend insight per zone
            if heat >= 0.8:
                trend = '<span style="color:#06B6D4; font-size:10px;">🔥 HOT</span>'
            elif heat >= 0.5:
                trend = '<span style="color:#4F46E5; font-size:10px;">📈 Active</span>'
            else:
                trend = '<span style="color:#475569; font-size:10px;">💤 Low</span>'

            safe_zone_label = _html.escape(zone_label)

            rows_html += f"""
            <tr style="border-bottom:1px solid #334155;">
                <td style="padding:12px 16px; white-space:nowrap;">
                    <div style="font-size:13px; font-weight:500; color:#cbd5e1;">{safe_zone_label}</div>
                    <div style="font-size:11px; margin-top:2px;">{trend}</div>
                </td>
                <td style="padding:12px 16px; text-align:right; color:#94a3b8; font-size:13px;">
                    {visits:,}
                </td>
                <td style="padding:12px 16px; text-align:right; color:#94a3b8; font-size:13px;">
                    {dwell_s}s
                </td>
                <td style="padding:12px 16px; min-width:90px;">
                    <div style="background:#0f172a; border-radius:2px; height:4px; margin-bottom:4px;">
                        <div style="background:{border}; width:{bar_pct}%; height:100%; border-radius:2px;"></div>
                    </div>
                    <div style="font-size:12px; font-weight:600; color:{border};">{heat:.2f}</div>
                </td>
                <td style="padding:12px 16px; text-align:center;">
                    <span style="background:{conf_bg}; color:{conf_tc}; font-size:10px;
                                 padding:2px 6px; border-radius:4px; font-weight:600;">{conf}</span>
                </td>
            </tr>
            """

        st.markdown(
            f"""
            <div style="background:#1e293b;
                        border:1px solid #334155; border-radius:8px; overflow:hidden;">
                <table style="width:100%; border-collapse:collapse; font-family:Inter,sans-serif;">
                    <thead>
                        <tr style="background:#0f172a; border-bottom:1px solid #334155;">
                            <th style="padding:12px 16px; color:#94a3b8; font-size:11px;
                                       font-weight:600; text-align:left;">ZONE</th>
                            <th style="padding:12px 16px; color:#94a3b8; font-size:11px;
                                       font-weight:600; text-align:right;">VISITS</th>
                            <th style="padding:12px 16px; color:#94a3b8; font-size:11px;
                                       font-weight:600; text-align:right;">DWELL</th>
                            <th style="padding:12px 16px; color:#94a3b8; font-size:11px;
                                       font-weight:600; text-align:left;">HEAT</th>
                            <th style="padding:12px 16px; color:#94a3b8; font-size:11px;
                                       font-weight:600; text-align:center;">CONF.</th>
                        </tr>
                    </thead>
                    <tbody>{rows_html}</tbody>
                </table>
            </div>
            """,
            unsafe_allow_html=True,
        )
