"""
Heatmap service — computes per-zone visit counts, average dwell time,
and a normalised heat score.

Heat score formula
------------------
    heat_score = (visits / max_visits) * 0.5 + (avg_dwell_ms / max_dwell_ms) * 0.5

Scores are in [0, 1] and normalised across zones.

Data confidence
---------------
When a zone has fewer than LOW_CONFIDENCE_THRESHOLD visitor sessions,
the ZoneHeat.data_confidence is set to "LOW" to signal that the
heatmap values may not be statistically reliable.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

import asyncpg

from config import get_settings
from models.heatmap import HeatmapResponse, ZoneHeat

logger = logging.getLogger(__name__)


class HeatmapService:
    """Compute zone heatmap for a store."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
        self._low_threshold = get_settings().low_confidence_session_threshold

    async def get_heatmap(
        self,
        store_id: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> HeatmapResponse:
        async with self.pool.acquire() as conn:
            rows = await self._zone_stats(conn, store_id, start, end)

        if not rows:
            return HeatmapResponse(store_id=store_id)

        zones: List[ZoneHeat] = []
        # Normalisation denominators
        max_visits = int(max((r["visits"] for r in rows), default=1) or 1)
        max_dwell = float(max((r["avg_dwell_ms"] or 0 for r in rows), default=1) or 1)

        for row in rows:
            visits = int(row["visits"] or 0)
            avg_dwell = float(row["avg_dwell_ms"] or 0)
            heat = round(
                (visits / max_visits) * 0.5 + (avg_dwell / max_dwell) * 0.5, 4
            )
            confidence = "LOW" if visits < self._low_threshold else None

            zones.append(
                ZoneHeat(
                    zone_id=row["zone_id"],
                    visits=visits,
                    avg_dwell_ms=round(avg_dwell, 2),
                    heat_score=heat,
                    data_confidence=confidence,
                )
            )

        # Sort by heat score descending
        zones.sort(key=lambda z: z.heat_score, reverse=True)
        return HeatmapResponse(store_id=store_id, zones=zones)

    # ------------------------------------------------------------------

    async def _zone_stats(
        self, conn, store_id: str, start, end
    ) -> list:
        """
        Aggregate ZONE_ENTER count and average dwell from ZONE_EXIT events
        per zone, excluding staff.
        """
        args = [store_id]
        window = ""
        if start:
            args.append(start)
            window += f" AND timestamp >= ${len(args)}"
        if end:
            args.append(end)
            window += f" AND timestamp <= ${len(args)}"

        sql = f"""
            SELECT
                zone_id,
                COUNT(*) FILTER (WHERE event_type = 'ZONE_ENTER') AS visits,
                AVG(dwell_ms)  FILTER (WHERE event_type = 'ZONE_EXIT'
                                         AND dwell_ms IS NOT NULL)  AS avg_dwell_ms
            FROM events
            WHERE store_id = $1
              AND event_type IN ('ZONE_ENTER', 'ZONE_EXIT')
              AND is_staff = FALSE
              AND zone_id IS NOT NULL
              {window}
            GROUP BY zone_id
            ORDER BY visits DESC
        """
        return await conn.fetch(sql, *args)
