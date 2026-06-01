"""
Anomaly detection service.

Detects three types of anomalies using statistical baselines:

QUEUE_SPIKE
-----------
Current queue depth is > QUEUE_SPIKE_MULTIPLIER × (30-day avg queue depth).
Severity scales with excess: >2× = MEDIUM, >3× = HIGH, >5× = CRITICAL.

CONVERSION_DROP
---------------
Today's conversion rate is < CONVERSION_DROP_THRESHOLD × (30-day avg).
Severity: <80% of baseline = MEDIUM, <60% = HIGH, <40% = CRITICAL.

DEAD_ZONE
---------
A shopping zone has received < DEAD_ZONE_MIN_VISITS visits in the last hour
despite the store being active (at least one ENTRY event in that period).
Severity: always MEDIUM (informational).

Anomalies are also persisted to the anomalies table for history.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import asyncpg

from api.models.anomalies import Anomaly, AnomalyResponse

logger = logging.getLogger(__name__)

_QUEUE_SPIKE_MULTIPLIER = 2.0
_CONVERSION_DROP_THRESHOLD = 0.80   # alert if today < 80% of baseline
_DEAD_ZONE_MIN_VISITS = 3
_DEAD_ZONE_WINDOW_HOURS = 1
_BASELINE_DAYS = 30


class AnomalyService:
    """Detect and persist store anomalies."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def get_anomalies(
        self,
        store_id: str,
        since: Optional[datetime] = None,
    ) -> AnomalyResponse:
        """
        Detect current anomalies and return them.

        Parameters
        ----------
        store_id : store to inspect.
        since    : if provided, only return anomalies detected after this time.
                   Also used as the "now" reference for detection windows.
        """
        now = since or datetime.now(tz=timezone.utc)
        anomalies: List[Anomaly] = []

        async with self.pool.acquire() as conn:
            anomalies += await self._detect_queue_spikes(conn, store_id, now)
            anomalies += await self._detect_conversion_drop(conn, store_id, now)
            anomalies += await self._detect_dead_zones(conn, store_id, now)

            # Persist new anomalies
            for a in anomalies:
                await self._persist(conn, store_id, a)

        # Also fetch recent historical anomalies from DB
        async with self.pool.acquire() as conn:
            historical = await self._fetch_recent(conn, store_id, since)

        # Merge, dedup by anomaly_id
        seen = {a.anomaly_id for a in anomalies}
        for h in historical:
            if h.anomaly_id not in seen:
                anomalies.append(h)

        # Sort by detected_at descending
        anomalies.sort(key=lambda a: a.detected_at, reverse=True)
        return AnomalyResponse(store_id=store_id, anomalies=anomalies)

    # ------------------------------------------------------------------
    # Detectors
    # ------------------------------------------------------------------

    async def _detect_queue_spikes(
        self, conn, store_id: str, now: datetime
    ) -> List[Anomaly]:
        """Compare current queue depth to 30-day baseline."""
        # Current depth (last 5 minutes)
        current_sql = """
            SELECT COUNT(*) FILTER (WHERE event_type = 'BILLING_QUEUE_JOIN')
                   - COUNT(*) FILTER (WHERE event_type = 'BILLING_QUEUE_ABANDON'
                                        OR event_type = 'EXIT')
            FROM events
            WHERE store_id = $1
              AND is_staff = FALSE
              AND timestamp >= $2
        """
        current_depth = await conn.fetchval(current_sql, store_id, now - timedelta(minutes=5))
        current_depth = max(int(current_depth or 0), 0)

        # Baseline: average daily queue depth over past 30 days
        baseline_sql = """
            SELECT AVG(daily_avg)
            FROM (
                SELECT DATE(timestamp) AS day,
                       COUNT(*) FILTER (WHERE event_type = 'BILLING_QUEUE_JOIN') AS daily_avg
                FROM events
                WHERE store_id = $1
                  AND is_staff = FALSE
                  AND timestamp >= $2
                GROUP BY DATE(timestamp)
            ) AS daily
        """
        baseline_avg = await conn.fetchval(
            baseline_sql, store_id, now - timedelta(days=_BASELINE_DAYS)
        )
        baseline_avg = float(baseline_avg or 0)

        anomalies = []
        if baseline_avg > 0 and current_depth > baseline_avg * _QUEUE_SPIKE_MULTIPLIER:
            ratio = current_depth / baseline_avg
            if ratio >= 5:
                severity = "CRITICAL"
            elif ratio >= 3:
                severity = "HIGH"
            else:
                severity = "MEDIUM"

            anomalies.append(
                Anomaly(
                    anomaly_id=_gen_id(),
                    type="QUEUE_SPIKE",
                    severity=severity,
                    detected_at=now,
                    details={
                        "current_depth": current_depth,
                        "baseline_avg": round(baseline_avg, 2),
                        "ratio": round(ratio, 2),
                    },
                    suggested_action=(
                        "Open additional billing counters immediately. "
                        "Consider activating express checkout lanes."
                    ),
                )
            )

        return anomalies

    async def _detect_conversion_drop(
        self, conn, store_id: str, now: datetime
    ) -> List[Anomaly]:
        """Compare today's conversion rate to 30-day baseline."""
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        today_sql = """
            SELECT
                COUNT(*) FILTER (WHERE made_purchase = TRUE) AS purchased,
                COUNT(*) AS total
            FROM visitor_sessions
            WHERE store_id = $1 AND is_staff = FALSE AND entry_time >= $2
        """
        today = await conn.fetchrow(today_sql, store_id, today_start)
        today_total = int(today["total"] or 0)
        if today_total < 10:
            return []   # Not enough data

        today_conv = (today["purchased"] or 0) / today_total

        baseline_sql = """
            SELECT
                COUNT(*) FILTER (WHERE made_purchase = TRUE)::FLOAT /
                NULLIF(COUNT(*), 0) AS conv_rate
            FROM visitor_sessions
            WHERE store_id = $1
              AND is_staff = FALSE
              AND entry_time >= $2
              AND entry_time < $3
        """
        baseline_conv = await conn.fetchval(
            baseline_sql, store_id,
            now - timedelta(days=_BASELINE_DAYS),
            today_start,
        )
        baseline_conv = float(baseline_conv or 0)

        anomalies = []
        if baseline_conv > 0 and today_conv < baseline_conv * _CONVERSION_DROP_THRESHOLD:
            ratio = today_conv / baseline_conv
            if ratio < 0.40:
                severity = "CRITICAL"
            elif ratio < 0.60:
                severity = "HIGH"
            else:
                severity = "MEDIUM"

            anomalies.append(
                Anomaly(
                    anomaly_id=_gen_id(),
                    type="CONVERSION_DROP",
                    severity=severity,
                    detected_at=now,
                    details={
                        "today_conversion_rate": round(today_conv, 4),
                        "baseline_conversion_rate": round(baseline_conv, 4),
                        "ratio": round(ratio, 4),
                    },
                    suggested_action=(
                        "Review staff deployment and promotion effectiveness. "
                        "Check if product placement or queue experience is deterring purchases."
                    ),
                )
            )

        return anomalies

    async def _detect_dead_zones(
        self, conn, store_id: str, now: datetime
    ) -> List[Anomaly]:
        """Find shopping zones with very low traffic in the past hour."""
        window_start = now - timedelta(hours=_DEAD_ZONE_WINDOW_HOURS)

        # Is the store active at all?
        active_entries = await conn.fetchval(
            """
            SELECT COUNT(*) FROM events
            WHERE store_id = $1
              AND event_type = 'ENTRY'
              AND is_staff = FALSE
              AND timestamp >= $2
            """,
            store_id,
            window_start,
        )
        if not active_entries or active_entries < 5:
            return []   # Store has low traffic overall — not an anomaly

        # Find zones with very few visits in the window
        sql = """
            SELECT zone_id, COUNT(*) AS visits
            FROM events
            WHERE store_id = $1
              AND event_type = 'ZONE_ENTER'
              AND is_staff = FALSE
              AND zone_id IS NOT NULL
              AND timestamp >= $2
            GROUP BY zone_id
            HAVING COUNT(*) < $3
        """
        dead_rows = await conn.fetch(sql, store_id, window_start, _DEAD_ZONE_MIN_VISITS)

        anomalies = []
        for row in dead_rows:
            anomalies.append(
                Anomaly(
                    anomaly_id=_gen_id(),
                    type="DEAD_ZONE",
                    severity="MEDIUM",
                    detected_at=now,
                    details={
                        "zone_id": row["zone_id"],
                        "visits_in_last_hour": int(row["visits"]),
                        "store_entries_in_period": int(active_entries),
                    },
                    suggested_action=(
                        f"Zone '{row['zone_id']}' shows very low traffic. "
                        "Consider repositioning products, improving signage, "
                        "or running a promotion to drive foot traffic to this area."
                    ),
                )
            )

        return anomalies

    # ------------------------------------------------------------------
    # Persistence & History
    # ------------------------------------------------------------------

    async def _persist(self, conn, store_id: str, anomaly: Anomaly) -> None:
        import json
        try:
            await conn.execute(
                """
                INSERT INTO anomalies
                    (anomaly_id, store_id, anomaly_type, severity, detected_at,
                     details, suggested_action)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (anomaly_id) DO NOTHING
                """,
                anomaly.anomaly_id,
                store_id,
                anomaly.type,
                anomaly.severity,
                anomaly.detected_at,
                json.dumps(anomaly.details),
                anomaly.suggested_action,
            )
        except Exception as exc:
            logger.warning("Failed to persist anomaly %s: %s", anomaly.anomaly_id, exc)

    async def _fetch_recent(
        self, conn, store_id: str, since: Optional[datetime]
    ) -> List[Anomaly]:
        cutoff = since or (datetime.now(tz=timezone.utc) - timedelta(hours=24))
        import json as _json
        rows = await conn.fetch(
            """
            SELECT anomaly_id, anomaly_type, severity, detected_at,
                   details, suggested_action
            FROM anomalies
            WHERE store_id = $1 AND detected_at >= $2
            ORDER BY detected_at DESC
            LIMIT 50
            """,
            store_id,
            cutoff,
        )
        result = []
        for row in rows:
            result.append(
                Anomaly(
                    anomaly_id=str(row["anomaly_id"]),
                    type=row["anomaly_type"],
                    severity=row["severity"],
                    detected_at=row["detected_at"],
                    details=_json.loads(row["details"]) if isinstance(row["details"], str) else dict(row["details"]),
                    suggested_action=row["suggested_action"],
                )
            )
        return result


def _gen_id() -> str:
    import uuid
    return str(uuid.uuid4())
