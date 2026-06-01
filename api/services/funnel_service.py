"""
Funnel service — computes the session-based conversion funnel.

Funnel stages
-------------
1. Entry        : total non-staff unique sessions
2. Zone Visit   : sessions that visited at least one shopping zone
3. Billing Queue: sessions that reached_billing = TRUE
4. Purchase     : sessions that made_purchase = TRUE

Each stage includes:
- count         : absolute count
- pct           : percentage of Entry stage
- drop_off      : percentage that dropped off from previous stage
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import asyncpg

from api.models.funnel import FunnelResponse, FunnelStage

logger = logging.getLogger(__name__)


class FunnelService:
    """Compute conversion funnel for a store over an optional time window."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def get_funnel(
        self,
        store_id: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> FunnelResponse:
        async with self.pool.acquire() as conn:
            rows = await self._funnel_counts(conn, store_id, start, end)
            reentry_sessions = await self._reentry_count(conn, store_id, start, end)

        if not rows:
            return FunnelResponse(store_id=store_id)

        total_entry = int(rows.get("entry", 0))
        total_zone = int(rows.get("zone_visit", 0))
        total_billing = int(rows.get("billing", 0))
        total_purchase = int(rows.get("purchase", 0))

        stages = []
        counts = [
            ("Entry", total_entry),
            ("Zone Visit", total_zone),
            ("Billing Queue", total_billing),
            ("Purchase", total_purchase),
        ]

        prev_count = total_entry or 1  # avoid division by zero

        for i, (label, count) in enumerate(counts):
            pct = round(count / (total_entry or 1) * 100, 2)
            drop_off: Optional[float] = None
            if i > 0:
                prev = counts[i - 1][1] or 1
                drop_off = round((prev - count) / prev * 100, 2)

            stages.append(
                FunnelStage(stage=label, count=count, pct=pct, drop_off=drop_off)
            )

        return FunnelResponse(
            store_id=store_id,
            funnel=stages,
            reentry_sessions=reentry_sessions,
        )

    # ------------------------------------------------------------------

    async def _funnel_counts(
        self, conn, store_id: str, start, end
    ) -> dict:
        """
        Single query: count sessions at each funnel stage.
        """
        args = [store_id]
        window = ""
        if start:
            args.append(start)
            window += f" AND entry_time >= ${len(args)}"
        if end:
            args.append(end)
            window += f" AND entry_time <= ${len(args)}"

        sql = f"""
            SELECT
                COUNT(*) AS entry,
                COUNT(*) FILTER (
                    WHERE array_length(zones_visited, 1) > 0
                ) AS zone_visit,
                COUNT(*) FILTER (
                    WHERE reached_billing = TRUE
                ) AS billing,
                COUNT(*) FILTER (
                    WHERE made_purchase = TRUE
                ) AS purchase
            FROM visitor_sessions
            WHERE store_id = $1
              AND is_staff = FALSE
              {window}
        """
        row = await conn.fetchrow(sql, *args)
        return dict(row) if row else {}

    async def _reentry_count(
        self, conn, store_id: str, start, end
    ) -> int:
        args = [store_id]
        window = ""
        if start:
            args.append(start)
            window += f" AND entry_time >= ${len(args)}"
        if end:
            args.append(end)
            window += f" AND entry_time <= ${len(args)}"

        sql = f"""
            SELECT COUNT(*)
            FROM visitor_sessions
            WHERE store_id = $1
              AND is_staff = FALSE
              AND is_reentry = TRUE
              {window}
        """
        return int(await conn.fetchval(sql, *args) or 0)
