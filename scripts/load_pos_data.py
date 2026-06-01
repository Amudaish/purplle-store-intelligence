"""
scripts/load_pos_data.py

Reads data/pos_transactions.csv and bulk-loads POS transactions into
the pos_transactions table, then runs POS matching for all stores.

CSV format (header row required)
---------------------------------
store_id,transaction_id,timestamp,basket_value_inr

Usage
-----
    python scripts/load_pos_data.py [--csv data/pos_transactions.csv] [--dsn <dsn>]
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import logging
from pathlib import Path

import asyncpg

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_DEFAULT_CSV = Path("data") / "pos_transactions.csv"
_DEFAULT_DSN = "postgresql://store_intel:store_intel_pass@localhost:5432/store_intelligence"


async def load_pos(csv_path: Path, dsn: str) -> None:
    if not csv_path.exists():
        logger.error("POS CSV not found: %s", csv_path)
        return

    conn = await asyncpg.connect(dsn)
    inserted = 0
    skipped = 0

    try:
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    result = await conn.execute(
                        """
                        INSERT INTO pos_transactions
                            (transaction_id, store_id, timestamp, basket_value_inr)
                        VALUES ($1, $2, $3::TIMESTAMPTZ, $4)
                        ON CONFLICT (transaction_id) DO NOTHING
                        """,
                        row["transaction_id"],
                        row["store_id"],
                        row["timestamp"],
                        float(row["basket_value_inr"]),
                    )
                    if result.endswith("1"):
                        inserted += 1
                    else:
                        skipped += 1
                except Exception as exc:
                    logger.warning("Skipping row %s: %s", row, exc)
                    skipped += 1

        logger.info(
            "POS load complete: inserted=%d, skipped=%d (duplicates/errors)",
            inserted, skipped,
        )

        # Run POS matching for each store that has transactions
        store_ids = await conn.fetch(
            "SELECT DISTINCT store_id FROM pos_transactions"
        )
        for record in store_ids:
            store_id = record["store_id"]
            matched = await _match_store(conn, store_id)
            logger.info(
                "POS matching: store=%s, newly_matched_sessions=%d",
                store_id, matched,
            )

    finally:
        await conn.close()


async def _match_store(conn: asyncpg.Connection, store_id: str) -> int:
    """Inline POS matching — mirrors POSMatcher logic without the service layer."""
    from datetime import timedelta

    from api.config import get_settings
    window = timedelta(minutes=get_settings().pos_match_window_minutes)

    transactions = await conn.fetch(
        """
        SELECT transaction_id, timestamp, basket_value_inr
        FROM pos_transactions
        WHERE store_id = $1
        ORDER BY timestamp
        """,
        store_id,
    )

    matched = 0
    for txn in transactions:
        txn_ts = txn["timestamp"]
        low = txn_ts - window
        high = txn_ts + window
        result = await conn.fetch(
            """
            UPDATE visitor_sessions
            SET made_purchase = TRUE
            WHERE session_id = (
                SELECT session_id FROM visitor_sessions
                WHERE store_id = $1
                  AND reached_billing = TRUE
                  AND is_staff = FALSE
                  AND made_purchase = FALSE
                  AND exit_time BETWEEN $2 AND $3
                ORDER BY ABS(EXTRACT(EPOCH FROM (exit_time - $4))) ASC
                LIMIT 1
            )
            RETURNING session_id
            """,
            store_id, low, high, txn_ts,
        )
        if result:
            matched += 1
    return matched


def main() -> None:
    p = argparse.ArgumentParser(description="Load POS transactions into PostgreSQL")
    p.add_argument("--csv", default=str(_DEFAULT_CSV), help="Path to pos_transactions.csv")
    p.add_argument("--dsn", default=_DEFAULT_DSN, help="PostgreSQL DSN")
    args = p.parse_args()
    asyncio.run(load_pos(Path(args.csv), args.dsn))


if __name__ == "__main__":
    main()
