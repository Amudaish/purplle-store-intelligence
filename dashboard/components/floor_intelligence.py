"""
Floor Intelligence — Hero heatmap with zone grid sidebar.
The most visually prominent element in the Operations tab.
"""

from __future__ import annotations
import html as _html
import streamlit as st
import plotly.graph_objects as go


# ── Zone layout grid (normalised col/row positions) ──────────────────────
_GRID: dict[str, dict] = {
    "entrance":  {"col": 1, "row": 3, "label": "Entrance"},
    "haircare":  {"col": 0, "row": 0, "label": "Haircare"},
    "skincare":  {"col": 1, "row": 0, "label": "Skincare"},
    "fragrance": {"col": 0, "row": 1, "label": "Fragrance"},
    "billing":   {"col": 2, "row": 2, "label": "Billing"},
    "checkout":  {"col": 2, "row": 2, "label": "Checkout"},
    "cosmetics": {"col": 2, "row": 0, "label": "Cosmetics"},
    "wellness":  {"col": 0, "row": 2, "label": "Wellness"},
}


def _heat_style(heat: float) -> tuple[str, str, str]:
    """Returns (fill_rgba, border_hex, text_color)."""
    if heat >= 0.85:
        return "rgba(6,182,212,0.22)",  "#06B6D4", "#06B6D4"
    if heat >= 0.65:
        return "rgba(99,102,241,0.22)", "#6366F1", "#818CF8"
    if heat >= 0.40:
        return "rgba(124,58,237,0.18)", "#7C3AED", "#A78BFA"
    if heat >= 0.20:
        return "rgba(30,58,95,0.55)",   "#1E3A5F", "#4A6080"
    return "rgba(9,18,30,0.70)",        "#0F1C2E", "#334155"


def _build_floor_fig(zones: list) -> go.Figure:
    CELL_W, CELL_H, GAP = 1.6, 1.1, 0.10

    positioned: list[dict] = []
    auto_col, auto_row = 0, 4

    for zone in zones:
        zid   = zone["zone_id"].lower()
        heat  = zone.get("heat_score", 0.0)
        label = zone.get("zone_id", "").replace("_", " ").title()
        if zid in _GRID:
            g    = _GRID[zid]
            col, row, label = g["col"], g["row"], g["label"]
        else:
            col, row = auto_col, auto_row
            auto_col += 1
        positioned.append({
            "col": col, "row": row, "label": label, "heat": heat,
            "visits": zone.get("visits", 0),
            "dwell_s": round(zone.get("avg_dwell_ms", 0) / 1000, 1),
            "conf": zone.get("data_confidence") or "OK",
        })

    max_col = max((p["col"] for p in positioned), default=2)
    max_row = max((p["row"] for p in positioned), default=3)
    total_w = (max_col + 1) * (CELL_W + GAP)
    total_h = (max_row + 1) * (CELL_H + GAP)

    fig = go.Figure()

    # Subtle background grid
    for c in range(max_col + 2):
        x = c * (CELL_W + GAP) - GAP / 2
        fig.add_shape(type="line", x0=x, y0=0, x1=x, y1=total_h,
                      line=dict(color="rgba(30,58,95,0.25)", width=0.5, dash="dot"))
    for r in range(max_row + 2):
        y = r * (CELL_H + GAP) - GAP / 2
        fig.add_shape(type="line", x0=0, y0=y, x1=total_w, y1=y,
                      line=dict(color="rgba(30,58,95,0.25)", width=0.5, dash="dot"))

    for p in positioned:
        col, row = p["col"], p["row"]
        x0 = col * (CELL_W + GAP)
        x1 = x0 + CELL_W
        y0 = (max_row - row) * (CELL_H + GAP)
        y1 = y0 + CELL_H
        fill, border, text_c = _heat_style(p["heat"])
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2

        # Glow for hot zones
        if p["heat"] >= 0.65:
            fig.add_shape(type="rect",
                x0=x0 - 0.05, y0=y0 - 0.05, x1=x1 + 0.05, y1=y1 + 0.05,
                fillcolor=f"rgba(6,182,212,{0.05 + p['heat']*0.08})",
                line=dict(width=0), opacity=0.6)

        # Zone rectangle
        fig.add_shape(type="rect", x0=x0, y0=y0, x1=x1, y1=y1,
                      fillcolor=fill, line=dict(color=border, width=1.5))

        # Heat intensity bar (bottom of cell)
        bar_w = CELL_W * p["heat"]
        if bar_w > 0:
            fig.add_shape(type="rect",
                x0=x0, y0=y0, x1=x0 + bar_w, y1=y0 + 0.05,
                fillcolor=border, line=dict(width=0), opacity=0.7)

        # Zone label
        fig.add_annotation(x=cx, y=cy + 0.20,
            text=f"<b>{p['label'].upper()}</b>",
            showarrow=False,
            font=dict(size=11, color="#D8E8FF", family="Space Grotesk"),
            xanchor="center", yanchor="middle")

        # Visit count
        fig.add_annotation(x=cx, y=cy - 0.05,
            text=f"{p['visits']:,} visits",
            showarrow=False,
            font=dict(size=9, color=text_c, family="Inter"),
            xanchor="center", yanchor="middle")

        # Heat score
        fig.add_annotation(x=cx, y=cy - 0.25,
            text=f"Heat {p['heat']*100:.0f}%  ·  {p['dwell_s']}s dwell",
            showarrow=False,
            font=dict(size=8, color="rgba(74,96,128,0.85)", family="Inter"),
            xanchor="center", yanchor="middle")

        # LOW DATA badge
        if p["conf"] == "LOW":
            fig.add_annotation(x=x1 - 0.06, y=y1 - 0.08,
                text="LOW DATA",
                showarrow=False,
                font=dict(size=7, color="#F87171", family="Inter"),
                xanchor="right", yanchor="top",
                bgcolor="rgba(59,10,10,0.85)", borderpad=2)

    # Entrance arrow
    cx_e = total_w / 2
    fig.add_annotation(x=cx_e, y=-0.22, text="▲  STORE ENTRANCE",
        showarrow=False, font=dict(size=9, color="#1E3A5F", family="Space Grotesk"),
        xanchor="center")
    fig.add_shape(type="line",
        x0=cx_e - 0.5, y0=-0.08, x1=cx_e + 0.5, y1=-0.08,
        line=dict(color="#1E3A5F", width=1.5))

    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(6,11,20,0.0)",
        xaxis=dict(visible=False, range=[-0.2, total_w + 0.2]),
        yaxis=dict(visible=False, range=[-0.45, total_h + 0.15], scaleanchor="x", scaleratio=1),
        height=max(400, (max_row + 1) * 165 + 80),
        margin=dict(l=0, r=0, t=8, b=24),
    )
    return fig


def _zone_color_for_heat(heat: float) -> str:
    if heat >= 0.85: return "#06B6D4"
    if heat >= 0.65: return "#6366F1"
    if heat >= 0.40: return "#7C3AED"
    if heat >= 0.20: return "#2563EB"
    return "#1E3A5F"


def render_floor_intelligence(heatmap_data: dict) -> None:
    zones = heatmap_data.get("zones", [])
    if not zones:
        st.markdown(
            '<div class="no-data"><div class="no-data-title">Floor Map Unavailable</div>'
            '<div class="no-data-sub">No zone data received from the heatmap API.</div></div>',
            unsafe_allow_html=True,
        )
        return

    # Sort zones: hottest first for display
    zones_sorted = sorted(zones, key=lambda z: z.get("heat_score", 0), reverse=True)

    col_map, col_grid = st.columns([3, 2], gap="medium")

    # ── Left: Hero Floor Map ──
    with col_map:
        st.markdown(
            """
            <div class="floor-wrap">
                <div class="floor-header">
                    <span class="floor-title">Store Floor Intelligence</span>
                    <span class="floor-live-tag">
                        <span style="width:5px;height:5px;border-radius:50%;background:#06B6D4;
                                     animation:blink 1.5s infinite;display:inline-block;"></span>
                        LIVE THERMAL
                    </span>
                </div>
                <div class="floor-body">
                    <div class="floor-legend">
                        <div class="floor-legend-item" style="color:#06B6D4;">
                            <div class="fl-dot" style="background:#06B6D4;"></div> HOT &ge;85%
                        </div>
                        <div class="floor-legend-item" style="color:#6366F1;">
                            <div class="fl-dot" style="background:#6366F1;"></div> WARM 65&ndash;84%
                        </div>
                        <div class="floor-legend-item" style="color:#7C3AED;">
                            <div class="fl-dot" style="background:#7C3AED;"></div> ACTIVE 40&ndash;64%
                        </div>
                        <div class="floor-legend-item" style="color:#4A6080;">
                            <div class="fl-dot" style="background:#1E3A5F;"></div> COLD &lt;40%
                        </div>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        floor_fig = _build_floor_fig(zones)
        st.plotly_chart(
            floor_fig, use_container_width=True,
            config={"displayModeBar": False, "staticPlot": True},
        )

    # ── Right: Zone Analytics Grid ──
    with col_grid:
        rows_html = ""
        for i, z in enumerate(zones_sorted):
            heat      = z.get("heat_score", 0.0)
            visits    = z.get("visits", 0)
            dwell_s   = round(z.get("avg_dwell_ms", 0) / 1000, 1)
            zn        = _html.escape(z["zone_id"].replace("_", " ").title())
            conf      = z.get("data_confidence") or "OK"
            color     = _zone_color_for_heat(heat)
            bar_pct   = int(heat * 100)
            conf_color = "#EF4444" if conf == "LOW" else "#10B981"
            conf_bg    = "#EF444418" if conf == "LOW" else "#10B98118"

            rows_html += f"""
            <div class="zone-row">
                <div class="zone-rank">#{i+1}</div>
                <div class="zone-info">
                    <div class="zone-name">{zn}</div>
                    <div class="zone-meta">{visits:,} visits &middot; {dwell_s}s dwell</div>
                </div>
                <div class="zone-right">
                    <div class="zone-heat-val" style="color:{color};">{heat*100:.0f}%</div>
                    <div class="zone-bar-track">
                        <div class="zone-bar-fill"
                             style="width:{bar_pct}%; background:{color};"></div>
                    </div>
                    <div class="zone-conf"
                         style="color:{conf_color}; background:{conf_bg};">{_html.escape(conf)}</div>
                </div>
            </div>
            """

        st.markdown(
            f"""
            <div class="zone-wrap">
                <div class="zone-header">
                    <div class="zone-header-title">Zone Analytics</div>
                </div>
                <div class="zone-list">{rows_html}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
