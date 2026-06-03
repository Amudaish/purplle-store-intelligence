"""
api/seed.py — Standalone store seeding script.

Can be run as a Render one-off job or manually after deployment.

Usage:
    DATABASE_URL="postgresql://..." python -m api.seed
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

import asyncpg

from database import CANONICAL_STORES, SCHEMA_SQL, SEED_STORES_SQL
import json

_SCHEMA_SQL = SCHEMA_SQL
_SEED_SQL = SEED_STORES_SQL

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


async def run_seed() -> int:
    raw = (
        os.environ.get("DATABASE_URL")
        or os.environ.get("DATABASE_URL_SYNC")
        or "postgresql://store_intel:store_intel_pass@localhost:5432/store_intelligence"
    )
    dsn = raw.replace("postgresql+asyncpg://", "postgresql://", 1).replace("postgres://", "postgresql://", 1)

    logger.info("Connecting to: %s", dsn.split("@")[-1] if "@" in dsn else dsn)
    try:
        conn = await asyncpg.connect(dsn)
    except Exception as exc:
        logger.error("Cannot connect: %s", exc)
        return 1

    try:
        db_name = await conn.fetchval("SELECT current_database()")
        schema  = await conn.fetchval("SELECT current_schema()")
        logger.info("Connected — db=%s schema=%s", db_name, schema)

        async with conn.transaction():
            await conn.execute(_SCHEMA_SQL)
        logger.info("Schema applied.")

        async with conn.transaction():
            empty = json.dumps({})
            for sid, name, city, open_t, close_t in CANONICAL_STORES:
                await conn.execute(_SEED_SQL, sid, name, city, open_t, close_t, empty)
                logger.info("  seeded: %s — %s", sid, name)

        rows = await conn.fetch("SELECT store_id, store_name FROM stores ORDER BY store_id")
        logger.info("Stores in database (%d):", len(rows))
        for r in rows:
            logger.info("  %s: %s", r["store_id"], r["store_name"])

        if len(rows) < len(CANONICAL_STORES):
            logger.error("Expected %d stores, found %d.", len(CANONICAL_STORES), len(rows))
            return 1

        logger.info("✅ Seed complete.")
        return 0
    except Exception as exc:
        logger.error("Seed failed: %s", exc, exc_info=True)
        return 1
    finally:
        await conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(run_seed()))
