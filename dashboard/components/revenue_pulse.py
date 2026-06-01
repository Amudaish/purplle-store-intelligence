"""
Revenue Pulse — 3-card strip: revenue opportunity, conversion loss, queue cost.
"""

from __future__ import annotations
import html as _html
import streamlit as st
from data_layer import (
    revenue_opportunity_inr, conversion_loss_inr,
    queue_cost_inr, AVG_TICKET_INR, BENCHMARK_CONV,
)


def render_revenue_pulse(metrics: dict, anomaly_data: dict) -> None:
    visitors = metrics.get("unique_visitors", 0)
    conv     = metrics.get("conversion_rate", 0.0)
    aband    = metrics.get("abandonment_rate", 0.0)

    rev_str, rev_amt     = revenue_opportunity_inr(metrics)
    loss_str, loss_amt   = conversion_loss_inr(metrics)
    queue_str, queue_amt = queue_cost_inr(metrics)

    # Confidence heuristics (data-driven proxies)
    rev_conf   = min(90, 60 + int(visitors / 10))
    loss_conf  = min(88, 55 + int(visitors / 8)) if conv < BENCHMARK_CONV else 95
    queue_conf = 91 if aband >= 0.20 else 78

    gap_pp = max(0.0, (BENCHMARK_CONV - conv) * 100)

    c1, c2, c3 = st.columns(3, gap="medium")

    # ── Card 1: Revenue Opportunity ──
    with c1:
        _pulse_card(
            eyebrow="Revenue Opportunity",
            value=_html.escape(rev_str),
            value_class="kv-green" if rev_amt > 0 else "",
            sub=f"{visitors:,} active visitors · ₹{AVG_TICKET_INR:,} avg ticket · 10% lift scenario",
            accent_color="#10B981",
            confidence=rev_conf,
            badge="UPSIDE",
            badge_color="#10B981",
            badge_bg="#10B98118",
        )

    # ── Card 2: Conversion Loss ──
    with c2:
        _pulse_card(
            eyebrow="Conversion Gap Loss",
            value=_html.escape(loss_str),
            value_class="kv-red" if loss_amt > 0 else "kv-green",
            sub=f"Current {conv*100:.1f}% vs {BENCHMARK_CONV*100:.0f}% benchmark · {gap_pp:.1f}pp gap",
            accent_color="#EF4444" if loss_amt > 0 else "#10B981",
            confidence=loss_conf,
            badge="GAP" if loss_amt > 0 else "ON TARGET",
            badge_color="#EF4444" if loss_amt > 0 else "#10B981",
            badge_bg="#EF444418" if loss_amt > 0 else "#10B98118",
        )

    # ── Card 3: Queue Abandonment Cost ──
    with c3:
        q_color = "#EF4444" if aband >= 0.4 else ("#F59E0B" if aband >= 0.2 else "#10B981")
        q_class = "kv-red" if aband >= 0.4 else ("kv-amber" if aband >= 0.2 else "kv-green")
        _pulse_card(
            eyebrow="Queue Abandonment Cost",
            value=_html.escape(queue_str),
            value_class=q_class,
            sub=f"{aband*100:.0f}% abandonment · {metrics.get('queue_depth', {}).get('current', 0)} in queue · ₹{AVG_TICKET_INR:,} avg ticket",
            accent_color=q_color,
            confidence=queue_conf,
            badge="HIGH RISK" if aband >= 0.4 else ("MONITOR" if aband >= 0.2 else "NOMINAL"),
            badge_color=q_color,
            badge_bg=f"{q_color}18",
        )


def _pulse_card(
    eyebrow: str, value: str, value_class: str, sub: str,
    accent_color: str, confidence: int,
    badge: str, badge_color: str, badge_bg: str,
) -> None:
    conf_fill_pct = confidence
    st.markdown(
        f"""
        <div class="pulse-card">
            <div class="pulse-card-accent-top"
                 style="background:linear-gradient(90deg,{accent_color},transparent);"></div>
            <div class="pulse-card-inner">
                <div class="pulse-eyebrow">{_html.escape(eyebrow)}</div>
                <div class="pulse-value {value_class}">{value}</div>
                <div class="pulse-sub">{_html.escape(sub)}</div>
            </div>
            <div class="pulse-footer">
                <div class="pulse-conf-wrap">
                    <div class="pulse-conf-track">
                        <div class="pulse-conf-fill"
                             style="width:{conf_fill_pct}%; background:{accent_color};"></div>
                    </div>
                    <div class="pulse-conf-label">Confidence: {conf_fill_pct}%</div>
                </div>
                <div class="pulse-badge"
                     style="color:{badge_color}; background:{badge_bg}; border:1px solid {badge_color}33;">
                    {_html.escape(badge)}
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
