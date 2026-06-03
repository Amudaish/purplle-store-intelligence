"""
POS transaction matcher.

Matches POS transactions to visitor sessions by:
  1. Narrowing to sessions with reached_billing=True within the store.
  2. Finding sessions whose exit_time is within ±POS_MATCH_WINDOW_MINUTES
     of the transaction timestamp.
  3. Marking matched sessions as made_purchase=True.

Called after each batch ingest to keep purchase data up-to-date.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import List

import asyncpg

from api.config import get_settings

logger = logging.getLogger(__name__)


class POSMatcher:
    """
    Reconciles POS transactions with visitor sessions to derive conversion rate.

    Usage
    -----
    matcher = POSMatcher(pool)
    matched = await matcher.match_store(store_id="store_001")
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
        self._window = timedelta(
            minutes=get_settings().pos_match_window_minutes
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def match_store(self, store_id: str) -> int:
        """
        Run POS matching for a store.

        Finds all unmatched POS transactions for the store and tries to
        link them to a visitor session.

        Returns the number of sessions newly marked as made_purchase=True.
        """
        matched = 0
        async with self.pool.acquire() as conn:
            transactions = await self._unmatched_transactions(conn, store_id)
            for txn in transactions:
                count = await self._match_transaction(conn, store_id, txn)
                matched += count
        logger.info(
            "POS matching complete", store_id=store_id, matched_sessions=matched
        )
        return matched

    async def load_transactions_from_csv(
        self, conn: asyncpg.Connection, csv_path: str
    ) -> int:
        """
        Bulk-load POS transactions from a CSV file into pos_transactions.

        CSV columns: store_id, transaction_id, timestamp, basket_value_inr
        Returns number of rows inserted.
        """
        import csv
        from pathlib import Path

        path = Path(csv_path)
        if not path.exists():
            logger.error("POS CSV not found: %s", csv_path)
            return 0

        inserted = 0
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    await conn.execute(
                        """
                        INSERT INTO pos_transactions
                            (transaction_id, store_id, timestamp, basket_value_inr)
                        VALUES ($1, $2, $3, $4)
                        ON CONFLICT (transaction_id) DO NOTHING
                        """,
                        row["transaction_id"],
                        row["store_id"],
                        row["timestamp"],
                        float(row["basket_value_inr"]),
                    )
                    inserted += 1
                except Exception as exc:
                    logger.warning("Skipping POS row %s: %s", row, exc)

        logger.info("Loaded %d POS transactions from %s", inserted, csv_path)
        return inserted

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _unmatched_transactions(
        self, conn: asyncpg.Connection, store_id: str
    ) -> List[asyncpg.Record]:
        """
        Return POS transactions that haven't been matched to a session yet.
        We identify "unmatched" as those within the last 24 hours to keep the
        query bounded.
        """
        sql = """
            SELECT pt.transaction_id, pt.timestamp, pt.basket_value_inr
            FROM pos_transactions pt
            WHERE pt.store_id = $1
              AND pt.timestamp > NOW() - INTERVAL '24 hours'
            ORDER BY pt.timestamp
        """
        return await conn.fetch(sql, store_id)

    async def _match_transaction(
        self,
        conn: asyncpg.Connection,
        store_id: str,
        txn: asyncpg.Record,
    ) -> int:
        """
        Attempt to match a single POS transaction to a visitor session.

        Matching logic:
        - Session must have reached_billing=True and is_staff=FALSE.
        - Session exit_time must be within ±window of transaction timestamp.
        - If multiple sessions match, pick the one with exit_time closest to
          the transaction timestamp.
        - Mark matched session as made_purchase=TRUE.
        """
        txn_ts = txn["timestamp"]
        low = txn_ts - self._window
        high = txn_ts + self._window

        sql = """
            UPDATE visitor_sessions
            SET made_purchase = TRUE
            WHERE session_id = (
                SELECT session_id
                FROM visitor_sessions
                WHERE store_id = $1
                  AND reached_billing = TRUE
                  AND is_staff = FALSE
                  AND made_purchase = FALSE
                  AND exit_time BETWEEN $2 AND $3
                ORDER BY ABS(EXTRACT(EPOCH FROM (exit_time - $4))) ASC
                LIMIT 1
            )
            RETURNING session_id
        """
        result = await conn.fetch(sql, store_id, low, high, txn_ts)
        if result:
            logger.debug(
                "POS matched",
                transaction_id=txn["transaction_id"],
                session_id=str(result[0]["session_id"]),
            )
            return 1
        return 0
