"""
Metrics service — aggregates store-level KPIs from the events and
visitor_sessions tables, excluding staff in all calculations.

Metrics returned
----------------
- unique_visitors       : distinct non-staff visitor sessions in window
- conversion_rate       : sessions with made_purchase / total non-staff sessions
- avg_dwell_time_ms     : average total_dwell_ms for completed non-staff sessions
- queue_depth.current   : count of visitors currently in billing zone
- queue_depth.avg       : average queue depth from BILLING_QUEUE_JOIN events
- queue_depth.max       : maximum queue depth observed
- abandonment_rate      : BILLING_QUEUE_ABANDON / BILLING_QUEUE_JOIN
- total_transactions    : POS transactions in window
- total_revenue_inr     : sum of basket_value_inr in window
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import asyncpg

from models.metrics import MetricsResponse, QueueMetrics

logger = logging.getLogger(__name__)


class MetricsService:
    """Compute store-level metrics for a given time window."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def get_metrics(
        self,
        store_id: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> Optional[MetricsResponse]:
        async with self.pool.acquire() as conn:
            # Log DB identity — verifies same database as ingestion
            db_name = await conn.fetchval("SELECT current_database()")
            schema  = await conn.fetchval("SELECT current_schema()")
            logger.info("get_metrics: store=%s db=%s schema=%s", store_id, db_name, schema)

            exists = await conn.fetchval(
                "SELECT 1 FROM stores WHERE store_id = $1", store_id
            )
            if not exists:
                store_count = await conn.fetchval("SELECT COUNT(*) FROM stores")
                logger.warning(
                    "store_id '%s' not found (db=%s schema=%s total_stores=%d)",
                    store_id, db_name, schema, store_count,
                )
                return None  # Router raises HTTP 404

            unique_visitors = await self._unique_visitors(conn, store_id, start, end)
            conversion_rate = await self._conversion_rate(conn, store_id, start, end)
            avg_dwell_ms = await self._avg_dwell(conn, store_id, start, end)
            queue = await self._queue_metrics(conn, store_id, start, end)
            abandonment = await self._abandonment_rate(conn, store_id, start, end)
            txn_count, revenue = await self._pos_metrics(conn, store_id, start, end)

        period = {
            "start": start.isoformat() if start else None,
            "end": end.isoformat() if end else None,
        }

        return MetricsResponse(
            store_id=store_id,
            period=period,
            unique_visitors=unique_visitors,
            conversion_rate=conversion_rate,
            avg_dwell_time_ms=avg_dwell_ms,
            queue_depth=queue,
            abandonment_rate=abandonment,
            total_transactions=txn_count,
            total_revenue_inr=revenue,
        )

    # ------------------------------------------------------------------
    # Internal queries
    # ------------------------------------------------------------------

    async def _unique_visitors(
        self, conn, store_id: str, start, end
    ) -> int:
        sql = """
            SELECT COUNT(DISTINCT visitor_id)
            FROM visitor_sessions
            WHERE store_id = $1
              AND is_staff = FALSE
              {window}
        """.format(window=_window_clause("entry_time", start, end, offset=2))
        args = _build_args(store_id, start, end)
        result = await conn.fetchval(sql, *args)
        return int(result or 0)

    async def _conversion_rate(
        self, conn, store_id: str, start, end
    ) -> float:
        sql = """
            SELECT
                COUNT(*) FILTER (WHERE made_purchase = TRUE) AS purchased,
                COUNT(*) AS total
            FROM visitor_sessions
            WHERE store_id = $1
              AND is_staff = FALSE
              {window}
        """.format(window=_window_clause("entry_time", start, end, offset=2))
        args = _build_args(store_id, start, end)
        row = await conn.fetchrow(sql, *args)
        if not row or not row["total"]:
            return 0.0
        return round(row["purchased"] / row["total"], 4)

    async def _avg_dwell(
        self, conn, store_id: str, start, end
    ) -> float:
        sql = """
            SELECT AVG(total_dwell_ms)
            FROM visitor_sessions
            WHERE store_id = $1
              AND is_staff = FALSE
              AND exit_time IS NOT NULL
              AND total_dwell_ms > 0
              {window}
        """.format(window=_window_clause("entry_time", start, end, offset=2))
        args = _build_args(store_id, start, end)
        result = await conn.fetchval(sql, *args)
        return round(float(result or 0), 2)

    async def _queue_metrics(
        self, conn, store_id: str, start, end
    ) -> QueueMetrics:
        # Current depth: active non-staff sessions that reached billing and haven't exited
        current = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM visitor_sessions
            WHERE store_id = $1
              AND is_staff = FALSE
              AND reached_billing = TRUE
              AND exit_time IS NULL
            """,
            store_id,
        )

        # Avg / Max queue depth from BILLING_QUEUE_JOIN metadata
        sql = """
            SELECT
                AVG((metadata->>'queue_depth')::FLOAT) AS avg_depth,
                MAX((metadata->>'queue_depth')::INT)   AS max_depth
            FROM events
            WHERE store_id = $1
              AND event_type = 'BILLING_QUEUE_JOIN'
              AND is_staff = FALSE
              AND metadata ? 'queue_depth'
              {window}
        """.format(window=_window_clause("timestamp", start, end, offset=2))
        args = _build_args(store_id, start, end)
        row = await conn.fetchrow(sql, *args)

        return QueueMetrics(
            current=int(current or 0),
            avg=round(float(row["avg_depth"] or 0), 2) if row else 0.0,
            max=int(row["max_depth"] or 0) if row else 0,
        )

    async def _abandonment_rate(
        self, conn, store_id: str, start, end
    ) -> float:
        sql = """
            SELECT
                COUNT(*) FILTER (WHERE event_type = 'BILLING_QUEUE_ABANDON') AS abandoned,
                COUNT(*) FILTER (WHERE event_type = 'BILLING_QUEUE_JOIN')    AS joined
            FROM events
            WHERE store_id = $1
              AND event_type IN ('BILLING_QUEUE_JOIN', 'BILLING_QUEUE_ABANDON')
              AND is_staff = FALSE
              {window}
        """.format(window=_window_clause("timestamp", start, end, offset=2))
        args = _build_args(store_id, start, end)
        row = await conn.fetchrow(sql, *args)
        if not row or not row["joined"]:
            return 0.0
        return round(row["abandoned"] / row["joined"], 4)

    async def _pos_metrics(
        self, conn, store_id: str, start, end
    ) -> tuple[int, float]:
        sql = """
            SELECT COUNT(*) AS txn_count, COALESCE(SUM(basket_value_inr), 0) AS revenue
            FROM pos_transactions
            WHERE store_id = $1
              {window}
        """.format(window=_window_clause("timestamp", start, end, offset=2))
        args = _build_args(store_id, start, end)
        row = await conn.fetchrow(sql, *args)
        if not row:
            return 0, 0.0
        return int(row["txn_count"]), float(row["revenue"])


# ── Query builder helpers ──────────────────────────────────────────────────────

def _window_clause(col: str, start, end, offset: int) -> str:
    """Build AND clauses for optional time window, using positional params."""
    clauses = []
    if start:
        clauses.append(f"AND {col} >= ${offset}")
        offset += 1
    if end:
        clauses.append(f"AND {col} <= ${offset}")
    return " ".join(clauses)


def _build_args(store_id: str, start, end) -> list:
    args = [store_id]
    if start:
        args.append(start)
    if end:
        args.append(end)
    return args
