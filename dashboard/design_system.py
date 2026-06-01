"""
Apex Retail Intelligence — Design System
Single-source CSS. Import and inject once at app startup.
"""

from __future__ import annotations

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600&display=swap');

/* ══ Reset & Base ══ */
*, *::before, *::after { box-sizing: border-box; }
html, body, [class*="css"] { font-family: 'Inter', sans-serif !important; }
.main, .stApp { background: #060B14 !important; }
.block-container { padding: 0 !important; max-width: 100% !important; }

/* ══ Hide Streamlit chrome ══ */
#MainMenu, footer, header { visibility: hidden !important; }
[data-testid="stToolbar"], [data-testid="stDecoration"] { display: none !important; }

/* ══ Hide sidebar ══ */
section[data-testid="stSidebar"] { display: none !important; }
[data-testid="collapsedControl"] { display: none !important; }

/* ══ Column gap normalization ══ */
[data-testid="stHorizontalBlock"] { gap: 12px !important; align-items: stretch !important; }

/* ══ Remove extra Streamlit padding ══ */
[data-testid="stVerticalBlock"] > [data-testid="stVerticalBlockBorderWrapper"] {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
}

/* ══ Tab content padding (replaces tab-body open/close div hack) ══ */
[data-testid="stTabContent"] > div:first-child > div:first-child {
    padding: 24px 24px 56px 24px !important;
}

/* ══ Native selectbox — command strip styling ══ */
[data-testid="stSelectbox"] label { display: none !important; }
[data-testid="stSelectbox"] > div > div {
    background: transparent !important;
    border: 1px solid #1E3A5F !important;
    color: #F0F6FF !important;
    font-size: 13px !important;
    font-weight: 600 !important;
    font-family: 'Space Grotesk', sans-serif !important;
    border-radius: 6px !important;
    min-height: 38px !important;
    padding: 0 12px !important;
    display: flex !important;
    align-items: center !important;
    transition: border-color 0.15s !important;
}
[data-testid="stSelectbox"] > div > div:hover {
    border-color: #2563EB !important;
}
[data-testid="stSelectbox"] svg { fill: #4A6080 !important; }
/* Vertically center the selectbox in the strip column */
[data-testid="stSelectbox"] { margin-top: 12px !important; }

/* ══ Tab nav ══ */
[data-testid="stTabsList"] {
    background: #060B14 !important;
    border-bottom: 1px solid #1E3A5F !important;
    padding: 0 24px !important;
    gap: 2px !important;
}
button[data-baseweb="tab"] {
    background: transparent !important;
    border: none !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 12px !important;
    font-weight: 600 !important;
    color: #4A6080 !important;
    padding: 12px 20px !important;
    border-radius: 6px 6px 0 0 !important;
    letter-spacing: 0.03em !important;
    transition: color 0.15s !important;
}
button[data-baseweb="tab"]:hover { color: #8AA0C0 !important; }
button[data-baseweb="tab"][aria-selected="true"] {
    color: #F0F6FF !important;
    background: transparent !important;
}
[data-baseweb="tab-highlight"] {
    background: #2563EB !important;
    height: 2px !important;
    border-radius: 2px !important;
}
[data-baseweb="tab-border"] { display: none !important; }
[data-testid="stTabContent"] { padding: 0 !important; }

/* ══ Plotly transparent container ══ */
[data-testid="stPlotlyChart"] { background: transparent !important; }
.js-plotly-plot .plotly, .js-plotly-plot .plotly .svg-container { background: transparent !important; }

/* ══ st.expander ══ */
[data-testid="stExpander"] {
    background: #0D1829 !important;
    border: 1px solid #1E3A5F !important;
    border-radius: 8px !important;
}
[data-testid="stExpander"] summary {
    font-family: 'Inter', sans-serif !important;
    font-size: 12px !important;
    font-weight: 600 !important;
    color: #8AA0C0 !important;
    padding: 12px 16px !important;
}
[data-testid="stExpander"] > div > div { padding: 12px 16px !important; }

/* ══ st.info / success / warning ══ */
[data-testid="stAlert"] {
    background: #0D1829 !important;
    border: 1px solid #1E3A5F !important;
    border-radius: 6px !important;
    color: #8AA0C0 !important;
}

/* ══ st.spinner ══ */
[data-testid="stSpinner"] p { color: #4A6080 !important; font-size: 12px !important; }

/* ══════════════════════════════════════════════════════
   COMPONENT STYLES
══════════════════════════════════════════════════════ */

/* ── Command Header Strip ── */
.cmd-strip {
    background: #060B14;
    border-bottom: 1px solid #1E3A5F;
    padding: 0 24px;
    display: flex;
    align-items: center;
    gap: 0;
    height: 62px;
}
.cmd-brand {
    display: flex;
    align-items: center;
    gap: 10px;
    padding-right: 20px;
    border-right: 1px solid #0F1F35;
    flex-shrink: 0;
}
.cmd-brand-mark {
    width: 32px; height: 32px;
    background: linear-gradient(150deg, #1D4ED8 0%, #0E7490 100%);
    border-radius: 8px;
    display: flex; align-items: center; justify-content: center;
    flex-shrink: 0;
    box-shadow: 0 0 0 1px rgba(6,182,212,0.25), 0 4px 12px rgba(37,99,235,0.3);
}
.cmd-brand-text { display: flex; flex-direction: column; gap: 1px; }
.cmd-brand-name {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 13px; font-weight: 700; color: #F0F6FF; letter-spacing: -0.01em;
}
.cmd-brand-sub {
    font-size: 9px; font-weight: 700; letter-spacing: 0.12em;
    text-transform: uppercase; color: #4A6080;
}
.cmd-store-wrap {
    padding: 0 20px;
    border-right: 1px solid #0F1F35;
    flex-shrink: 0;
}
.cmd-kpi-area {
    display: flex; align-items: center; gap: 0;
    flex: 1; justify-content: center; padding: 0 8px;
}
.cmd-kpi-item {
    display: flex; flex-direction: column; align-items: center;
    padding: 0 20px; border-right: 1px solid #0F1F35;
}
.cmd-kpi-item:first-child { border-left: 1px solid #0F1F35; }
.cmd-kpi-label {
    font-size: 9px; font-weight: 700; letter-spacing: 0.14em;
    text-transform: uppercase; color: #4A6080; margin-bottom: 2px;
}
.cmd-kpi-value {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 15px; font-weight: 700; color: #F0F6FF;
    line-height: 1; font-variant-numeric: tabular-nums;
}
.cmd-kpi-value.kv-green { color: #10B981; }
.cmd-kpi-value.kv-amber { color: #F59E0B; }
.cmd-kpi-value.kv-red   { color: #EF4444; }
.cmd-kpi-value.kv-cyan  { color: #06B6D4; }
.cmd-right {
    display: flex; align-items: center; gap: 10px;
    padding-left: 20px; flex-shrink: 0;
}
.sys-pill {
    display: flex; align-items: center; gap: 5px;
    font-size: 10px; font-weight: 700;
    padding: 4px 10px; border-radius: 4px; border: 1px solid;
    letter-spacing: 0.04em; font-family: 'Space Grotesk', sans-serif;
    white-space: nowrap;
}
.sys-pill-live { color: #10B981; border-color: #10B98133; background: #10B98110; }
.sys-pill-warn { color: #F59E0B; border-color: #F59E0B33; background: #F59E0B10; }
.sys-pill-err  { color: #EF4444; border-color: #EF444433; background: #EF444410; }
.sys-dot {
    width: 6px; height: 6px; border-radius: 50%;
    background: currentColor; animation: blink 2s infinite;
    flex-shrink: 0;
}
@keyframes blink { 0%,100%{opacity:1;} 50%{opacity:.35;} }
.refresh-tag {
    font-size: 9px; color: #4A6080; font-weight: 600;
    letter-spacing: 0.08em; text-transform: uppercase;
    padding-left: 2px;
}

/* ── Alert Banner ── */
.alert-banner {
    padding: 12px 24px;
    display: flex; align-items: center; gap: 14px;
    border-bottom: 1px solid transparent;
}
.alert-critical {
    background: linear-gradient(90deg, rgba(239,68,68,0.18) 0%, rgba(6,11,20,0.98) 65%);
    border-bottom-color: rgba(239,68,68,0.22);
}
.alert-elevated {
    background: linear-gradient(90deg, rgba(245,158,11,0.14) 0%, rgba(6,11,20,0.98) 65%);
    border-bottom-color: rgba(245,158,11,0.18);
}
.alert-nominal {
    background: linear-gradient(90deg, rgba(16,185,129,0.07) 0%, rgba(6,11,20,0.98) 65%);
    border-bottom-color: rgba(16,185,129,0.10);
}
.alert-pill {
    font-size: 9px; font-weight: 800; letter-spacing: 0.14em;
    text-transform: uppercase; padding: 3px 10px;
    border-radius: 3px; flex-shrink: 0;
    font-family: 'Space Grotesk', sans-serif;
}
.alert-pill-critical { color: #EF4444; background: #EF444418; border: 1px solid #EF444440; }
.alert-pill-elevated { color: #F59E0B; background: #F59E0B18; border: 1px solid #F59E0B40; }
.alert-pill-nominal  { color: #10B981; background: #10B98118; border: 1px solid #10B98140; }
.alert-msg { font-size: 13px; color: #94A3B8; flex: 1; line-height: 1.4; }
.alert-msg strong { color: #F0F6FF; font-weight: 600; }
.alert-cta {
    font-size: 10px; font-weight: 800; letter-spacing: 0.1em;
    text-transform: uppercase; color: #2563EB; flex-shrink: 0;
}
.alert-divider { width: 1px; height: 18px; background: #1E3A5F; flex-shrink: 0; }

/* ── Tab body (applied via CSS to native Streamlit tab content) ── */
.tab-body { padding: 24px 24px 56px 24px; }

/* ── Section label ── */
.sec-label {
    font-size: 9px; font-weight: 800; letter-spacing: 0.18em;
    text-transform: uppercase; color: #4A6080;
    display: flex; align-items: center; gap: 10px;
    margin-bottom: 16px; margin-top: 32px;
}
.sec-label-first { margin-top: 4px; }
.sec-label::after {
    content: ''; flex: 1; height: 1px;
    background: linear-gradient(90deg, #1E3A5F 0%, transparent 100%);
}

/* ── Revenue Pulse Cards ── */
.pulse-card {
    background: #0D1829;
    border: 1px solid #1E3A5F;
    border-radius: 8px;
    padding: 0;
    height: 100%;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    position: relative;
    transition: border-color 0.2s, box-shadow 0.2s;
    cursor: default;
}
.pulse-card:hover {
    border-color: #2563EB44;
    box-shadow: 0 4px 20px rgba(37,99,235,0.10);
}
.pulse-card-accent-top {
    height: 2px; width: 100%;
}
.pulse-card-inner { padding: 18px 20px; flex: 1; display: flex; flex-direction: column; }
.pulse-eyebrow {
    font-size: 9px; font-weight: 800; letter-spacing: 0.18em;
    text-transform: uppercase; color: #4A6080; margin-bottom: 8px;
}
.pulse-value {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 28px; font-weight: 700; line-height: 1;
    letter-spacing: -0.02em; font-variant-numeric: tabular-nums;
    margin-bottom: 6px;
}
.pulse-sub { font-size: 11px; color: #4A6080; line-height: 1.4; flex: 1; }
.pulse-footer {
    padding: 10px 20px 14px;
    border-top: 1px solid #0F1F35;
    display: flex; align-items: center; justify-content: space-between;
    gap: 8px;
}
.pulse-conf-wrap { display: flex; flex-direction: column; gap: 4px; flex: 1; }
.pulse-conf-track {
    height: 3px; background: #060B14;
    border-radius: 2px; overflow: hidden;
}
.pulse-conf-fill { height: 100%; border-radius: 2px; }
.pulse-conf-label {
    font-size: 9px; color: #4A6080; font-weight: 600;
    letter-spacing: 0.06em; white-space: nowrap;
}
.pulse-badge {
    font-size: 9px; font-weight: 800; letter-spacing: 0.08em;
    text-transform: uppercase; padding: 3px 7px; border-radius: 3px;
    flex-shrink: 0;
}

/* ── Floor Intelligence (Heatmap Hero) ── */
.floor-wrap {
    background: #0D1829;
    border: 1px solid #1E3A5F;
    border-radius: 8px; overflow: hidden;
}
.floor-header {
    padding: 13px 18px;
    background: #070E1C;
    border-bottom: 1px solid #1E3A5F;
    display: flex; align-items: center; justify-content: space-between;
}
.floor-title {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 12px; font-weight: 700; color: #F0F6FF;
    letter-spacing: 0.03em;
}
.floor-live-tag {
    font-size: 9px; font-weight: 800; letter-spacing: 0.1em;
    text-transform: uppercase; color: #06B6D4;
    background: #06B6D410; border: 1px solid #06B6D430;
    padding: 2px 8px; border-radius: 3px;
    display: flex; align-items: center; gap: 5px;
}
.floor-body { padding: 14px 16px; }
.floor-legend {
    display: flex; gap: 14px; margin-bottom: 10px; flex-wrap: wrap;
}
.floor-legend-item {
    display: flex; align-items: center; gap: 5px;
    font-size: 9px; font-weight: 700; letter-spacing: 0.08em;
    text-transform: uppercase;
}
.fl-dot { width: 8px; height: 8px; border-radius: 2px; }

/* ── Zone Analytics Grid ── */
.zone-wrap {
    background: #0D1829;
    border: 1px solid #1E3A5F;
    border-radius: 8px; overflow: hidden; height: 100%;
    display: flex; flex-direction: column;
}
.zone-header {
    padding: 13px 18px;
    background: #070E1C;
    border-bottom: 1px solid #1E3A5F;
    flex-shrink: 0;
}
.zone-header-title {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 12px; font-weight: 700; color: #F0F6FF;
    letter-spacing: 0.03em;
}
.zone-list { flex: 1; overflow-y: auto; }
.zone-row {
    padding: 11px 18px;
    border-bottom: 1px solid #0F1F35;
    display: flex; align-items: center; gap: 10px;
    transition: background 0.15s;
    cursor: default;
}
.zone-row:hover { background: rgba(37,99,235,0.05); }
.zone-row:last-child { border-bottom: none; }
.zone-rank {
    font-size: 10px; font-weight: 700; color: #4A6080;
    width: 16px; flex-shrink: 0;
    font-family: 'Space Grotesk', sans-serif;
}
.zone-info { flex: 1; min-width: 0; }
.zone-name {
    font-size: 12px; font-weight: 600; color: #CBD5E1;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    font-family: 'Space Grotesk', sans-serif;
}
.zone-meta { font-size: 10px; color: #4A6080; margin-top: 2px; }
.zone-right {
    display: flex; flex-direction: column; align-items: flex-end;
    gap: 3px; flex-shrink: 0;
}
.zone-heat-val {
    font-size: 13px; font-weight: 700;
    font-family: 'Space Grotesk', sans-serif;
    font-variant-numeric: tabular-nums;
}
.zone-bar-track {
    width: 56px; height: 3px;
    background: #060B14; border-radius: 2px; overflow: hidden;
}
.zone-bar-fill { height: 100%; border-radius: 2px; }
.zone-conf {
    font-size: 8px; font-weight: 800; letter-spacing: 0.08em;
    text-transform: uppercase; padding: 1px 5px; border-radius: 2px;
}

/* ── AI Action Center ── */
.ai-card {
    background: #0D1829;
    border: 1px solid #1E3A5F;
    border-radius: 8px; overflow: hidden; margin-bottom: 12px;
    transition: border-color 0.2s, box-shadow 0.2s;
    cursor: default;
}
.ai-card:hover {
    border-color: #2563EB55;
    box-shadow: 0 4px 24px rgba(37,99,235,0.12);
}
.ai-card-top {
    padding: 13px 18px;
    background: #070E1C;
    border-bottom: 1px solid #1E3A5F;
    display: flex; align-items: center; gap: 12px;
}
.ai-priority-num {
    font-size: 9px; font-weight: 800; letter-spacing: 0.14em;
    text-transform: uppercase; color: #4A6080;
    font-family: 'Space Grotesk', sans-serif;
    flex-shrink: 0;
}
.ai-signal-chip {
    font-size: 9px; font-weight: 800; letter-spacing: 0.1em;
    text-transform: uppercase; padding: 2px 8px;
    border-radius: 3px; flex-shrink: 0;
}
.ai-urgency-chip {
    font-size: 9px; font-weight: 800; letter-spacing: 0.1em;
    text-transform: uppercase; padding: 2px 8px;
    border-radius: 3px; flex-shrink: 0;
}
.ai-conf-area {
    margin-left: auto; display: flex; flex-direction: column;
    align-items: flex-end; gap: 3px; flex-shrink: 0;
}
.ai-conf-label { font-size: 9px; color: #4A6080; font-weight: 600; letter-spacing: 0.06em; }
.ai-conf-val {
    font-size: 14px; font-weight: 700; color: #06B6D4;
    font-family: 'Space Grotesk', sans-serif; line-height: 1;
}
.ai-card-body { padding: 16px 18px; }
.ai-recommendation {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 15px; font-weight: 700; color: #F0F6FF;
    line-height: 1.35; margin-bottom: 10px;
}
.ai-context { font-size: 12px; color: #8AA0C0; line-height: 1.55; margin-bottom: 14px; }
.ai-metrics-row { display: flex; gap: 10px; }
.ai-metric-block {
    flex: 1;
    background: #060B14; border: 1px solid #0F1F35;
    border-radius: 6px; padding: 11px 13px;
    display: flex; flex-direction: column; gap: 3px;
}
.ai-metric-lbl {
    font-size: 9px; font-weight: 700; letter-spacing: 0.12em;
    text-transform: uppercase; color: #4A6080;
}
.ai-metric-val {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 17px; font-weight: 700;
    font-variant-numeric: tabular-nums; line-height: 1;
}
.ai-card-footer {
    padding: 11px 18px;
    border-top: 1px solid #0F1F35;
    background: #060B14;
    display: flex; align-items: center; justify-content: space-between;
}
.ai-outcome { font-size: 12px; color: #8AA0C0; line-height: 1.4; }
.ai-outcome strong { color: #10B981; font-weight: 600; }
.ai-act {
    font-size: 10px; font-weight: 800; letter-spacing: 0.1em;
    text-transform: uppercase; color: #2563EB;
    cursor: pointer;
    transition: color 0.15s;
}
.ai-act:hover { color: #60A5FA; }

/* ── Sankey / Journey Panel ── */
.journey-wrap {
    background: #0D1829;
    border: 1px solid #1E3A5F;
    border-radius: 8px; overflow: hidden;
}
.journey-header {
    padding: 13px 18px;
    background: #070E1C;
    border-bottom: 1px solid #1E3A5F;
    display: flex; align-items: center; justify-content: space-between;
}
.journey-header-title {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 12px; font-weight: 700; color: #F0F6FF; letter-spacing: 0.03em;
}
.journey-stat-strip {
    display: grid; grid-template-columns: repeat(4, 1fr);
    border-top: 1px solid #1E3A5F;
}
.journey-stat {
    padding: 14px 18px;
    border-right: 1px solid #1E3A5F; text-align: center;
}
.journey-stat:last-child { border-right: none; }
.journey-stat-lbl {
    font-size: 9px; font-weight: 700; letter-spacing: 0.12em;
    text-transform: uppercase; color: #4A6080; margin-bottom: 4px;
}
.journey-stat-val {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 20px; font-weight: 700;
    font-variant-numeric: tabular-nums;
}

/* ── Queue Tab ── */
.queue-panel {
    background: #0D1829;
    border: 1px solid #1E3A5F;
    border-radius: 8px; padding: 22px;
    height: 100%; display: flex; flex-direction: column;
    align-items: center; justify-content: center; gap: 16px;
    text-align: center;
}
.q-ring {
    width: 130px; height: 130px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    flex-direction: column; border: 7px solid; position: relative;
}
.q-depth-val {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 42px; font-weight: 700; line-height: 1;
}
.q-depth-lbl {
    font-size: 9px; font-weight: 700; letter-spacing: 0.1em;
    text-transform: uppercase; color: #4A6080; margin-top: 2px;
}
.q-state-label {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 14px; font-weight: 700;
}
.q-desc { font-size: 12px; color: #4A6080; line-height: 1.5; max-width: 220px; }
.q-aband-row {
    display: flex; flex-direction: column; gap: 4px;
    width: 100%; max-width: 220px;
}
.q-aband-lbl { font-size: 10px; color: #4A6080; font-weight: 600; text-align: left; }
.q-aband-track { height: 6px; background: #060B14; border-radius: 3px; overflow: hidden; }
.q-aband-fill { height: 100%; border-radius: 3px; }
.q-aband-pct {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 16px; font-weight: 700;
}

.staff-panel {
    background: #0D1829;
    border: 1px solid #1E3A5F;
    border-radius: 8px; overflow: hidden; height: 100%;
}
.staff-panel-header {
    padding: 13px 18px;
    background: #070E1C;
    border-bottom: 1px solid #1E3A5F;
}
.staff-panel-title {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 12px; font-weight: 700; color: #F0F6FF; letter-spacing: 0.03em;
}
.staff-body { padding: 20px; }
.staff-directive {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 22px; font-weight: 700; line-height: 1.2;
    margin-bottom: 10px;
}
.staff-rationale { font-size: 12px; color: #8AA0C0; line-height: 1.55; margin-bottom: 18px; }
.staff-metric-row { display: flex; gap: 10px; }
.staff-metric {
    flex: 1; background: #060B14; border: 1px solid #0F1F35;
    border-radius: 6px; padding: 12px; text-align: center;
}
.staff-metric-val {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 18px; font-weight: 700; margin-bottom: 4px;
    font-variant-numeric: tabular-nums;
}
.staff-metric-lbl {
    font-size: 9px; font-weight: 700; letter-spacing: 0.1em;
    text-transform: uppercase; color: #4A6080;
}

/* ── Risk / Anomaly Tab ── */
.risk-overview {
    background: #0D1829; border: 1px solid #1E3A5F;
    border-radius: 8px; overflow: hidden; height: 100%;
}
.risk-overview-header {
    padding: 13px 18px;
    background: #070E1C;
    border-bottom: 1px solid #1E3A5F;
}
.risk-overview-title {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 12px; font-weight: 700; color: #F0F6FF; letter-spacing: 0.03em;
}
.risk-composite {
    padding: 24px 20px;
    display: flex; align-items: center; gap: 24px;
}
.risk-score-wrap { flex-shrink: 0; text-align: center; }
.risk-score-big {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 52px; font-weight: 700; line-height: 1;
    font-variant-numeric: tabular-nums;
}
.risk-score-lbl {
    font-size: 9px; font-weight: 700; letter-spacing: 0.12em;
    text-transform: uppercase; color: #4A6080; margin-top: 4px;
}
.risk-factors { flex: 1; }
.risk-factor-row {
    display: flex; align-items: center; justify-content: space-between;
    padding: 8px 0; border-bottom: 1px solid #0F1F35;
    font-size: 12px;
}
.risk-factor-row:last-child { border-bottom: none; }
.risk-factor-name { color: #8AA0C0; }
.risk-factor-val { font-weight: 700; color: #F0F6FF; font-family: 'Space Grotesk', sans-serif; }

.anom-card {
    background: #0D1829; border: 1px solid #1E3A5F;
    border-radius: 6px; padding: 14px 16px;
    margin-bottom: 8px; display: flex; gap: 12px;
    align-items: flex-start;
    transition: border-color 0.15s;
    cursor: default;
}
.anom-card:hover { border-color: #334155; }
.anom-accent { width: 3px; border-radius: 2px; align-self: stretch; flex-shrink: 0; min-height: 40px; }
.anom-body { flex: 1; }
.anom-type {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 13px; font-weight: 700; color: #F0F6FF; margin-bottom: 4px;
}
.anom-action { font-size: 12px; color: #8AA0C0; line-height: 1.45; }
.anom-ts { font-size: 10px; color: #4A6080; margin-top: 8px; }
.anom-badge-wrap { flex-shrink: 0; display: flex; flex-direction: column; align-items: flex-end; gap: 6px; }
.anom-badge {
    font-size: 9px; font-weight: 800; padding: 3px 8px;
    border-radius: 3px; letter-spacing: 0.1em; text-transform: uppercase;
    font-family: 'Space Grotesk', sans-serif;
}

/* ── Live Feed ── */
.live-feed-item {
    display: flex; align-items: center; gap: 10px;
    padding: 7px 0; border-bottom: 1px solid #0F1F35;
    font-size: 11px;
}
.live-feed-item:last-child { border-bottom: none; }
.live-feed-type {
    font-size: 9px; font-weight: 700; letter-spacing: 0.08em;
    text-transform: uppercase; padding: 2px 6px; border-radius: 3px;
    flex-shrink: 0; font-family: 'Space Grotesk', sans-serif;
}
.live-feed-zone { color: #8AA0C0; flex: 1; }
.live-feed-ts { font-size: 10px; color: #4A6080; flex-shrink: 0; font-variant-numeric: tabular-nums; }

/* ── No data state ── */
.no-data {
    padding: 40px 24px; text-align: center;
    color: #4A6080; background: #0D1829;
    border: 1px solid #1E3A5F; border-radius: 8px;
}
.no-data-title {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 14px; color: #8AA0C0; font-weight: 600; margin-bottom: 6px;
}
.no-data-sub { font-size: 12px; color: #4A6080; }
</style>
"""
