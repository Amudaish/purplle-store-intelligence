"""
scripts/load_store_layout.py

Reads data/store_layout.json and upserts all store records into
the PostgreSQL stores table.

Usage
-----
    python scripts/load_store_layout.py [--layout data/store_layout.json] [--dsn <dsn>]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path

import asyncpg

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_DEFAULT_LAYOUT = Path("data") / "store_layout.json"
_DEFAULT_DSN = "postgresql://store_intel:store_intel_pass@localhost:5432/store_intelligence"


async def load_layout(layout_path: Path, dsn: str) -> None:
    data = json.loads(layout_path.read_text(encoding="utf-8"))
    stores = data.get("stores", {})

    conn = await asyncpg.connect(dsn)
    try:
        for store_id, store in stores.items():
            await conn.execute(
                """
                INSERT INTO stores (store_id, store_name, city, open_time, close_time, layout)
                VALUES ($1, $2, $3, $4::TIME, $5::TIME, $6)
                ON CONFLICT (store_id) DO UPDATE
                    SET store_name = EXCLUDED.store_name,
                        city       = EXCLUDED.city,
                        open_time  = EXCLUDED.open_time,
                        close_time = EXCLUDED.close_time,
                        layout     = EXCLUDED.layout
                """,
                store_id,
                store.get("name"),
                store.get("city"),
                store.get("open_time", "09:00"),
                store.get("close_time", "21:00"),
                json.dumps(store),
            )
            logger.info("Upserted store: %s (%s)", store_id, store.get("name"))
    finally:
        await conn.close()

    logger.info("Loaded %d stores from %s", len(stores), layout_path)


def main() -> None:
    p = argparse.ArgumentParser(description="Load store layout into PostgreSQL")
    p.add_argument("--layout", default=str(_DEFAULT_LAYOUT), help="Path to store_layout.json")
    p.add_argument("--dsn", default=_DEFAULT_DSN, help="PostgreSQL DSN")
    args = p.parse_args()
    asyncio.run(load_layout(Path(args.layout), args.dsn))


if __name__ == "__main__":
    main()
