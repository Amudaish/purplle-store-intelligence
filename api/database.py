"""PostgreSQL database connection, schema management, and store seeding."""

import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import time as dtime
from typing import AsyncGenerator

import asyncpg

logger = logging.getLogger(__name__)

# Module-level connection pool
_pool: asyncpg.Pool | None = None

# ── DSN resolution ────────────────────────────────────────────────────────────
# Read DATABASE_URL directly from the environment — no pydantic layer.
# Render sets DATABASE_URL as:  postgresql://user:pass@host:5432/dbname
# asyncpg needs:                postgresql://user:pass@host:5432/dbname  (same)
# We only strip the +asyncpg driver tag if present (from .env files).

def _get_dsn() -> str:
    raw = (
        os.environ.get("DATABASE_URL")
        or os.environ.get("DATABASE_URL_SYNC")
        or "postgresql://store_intel:store_intel_pass@localhost:5432/store_intelligence"
    )
    # asyncpg uses plain postgresql://, not postgresql+asyncpg://
    raw = raw.replace("postgresql+asyncpg://", "postgresql://", 1)
    raw = raw.replace("postgres://", "postgresql://", 1)
    return raw


# ── DDL ───────────────────────────────────────────────────────────────────────

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS stores (
    store_id        VARCHAR(32)   PRIMARY KEY,
    store_name      VARCHAR(128),
    city            VARCHAR(64),
    open_time       TIME,
    close_time      TIME,
    layout          JSONB         NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS events (
    event_id        UUID            PRIMARY KEY,
    store_id        VARCHAR(32)     NOT NULL REFERENCES stores(store_id),
    camera_id       VARCHAR(32)     NOT NULL,
    visitor_id      VARCHAR(64)     NOT NULL,
    event_type      VARCHAR(32)     NOT NULL,
    timestamp       TIMESTAMPTZ     NOT NULL,
    zone_id         VARCHAR(32),
    dwell_ms        INTEGER,
    is_staff        BOOLEAN         NOT NULL DEFAULT FALSE,
    confidence      FLOAT           NOT NULL,
    metadata        JSONB           DEFAULT '{}',
    created_at      TIMESTAMPTZ     DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS visitor_sessions (
    session_id      UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id        VARCHAR(32)     NOT NULL REFERENCES stores(store_id),
    visitor_id      VARCHAR(64)     NOT NULL,
    is_staff        BOOLEAN         NOT NULL DEFAULT FALSE,
    entry_time      TIMESTAMPTZ     NOT NULL,
    exit_time       TIMESTAMPTZ,
    is_reentry      BOOLEAN         DEFAULT FALSE,
    zones_visited   TEXT[]          DEFAULT '{}',
    reached_billing BOOLEAN         DEFAULT FALSE,
    made_purchase   BOOLEAN         DEFAULT FALSE,
    total_dwell_ms  INTEGER         DEFAULT 0,
    created_at      TIMESTAMPTZ     DEFAULT NOW(),
    UNIQUE (store_id, visitor_id, entry_time)
);

CREATE TABLE IF NOT EXISTS pos_transactions (
    transaction_id  VARCHAR(64)     PRIMARY KEY,
    store_id        VARCHAR(32)     NOT NULL REFERENCES stores(store_id),
    timestamp       TIMESTAMPTZ     NOT NULL,
    basket_value_inr DECIMAL(10,2)  NOT NULL
);

CREATE TABLE IF NOT EXISTS anomalies (
    anomaly_id      UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id        VARCHAR(32)     NOT NULL REFERENCES stores(store_id),
    anomaly_type    VARCHAR(32)     NOT NULL,
    severity        VARCHAR(16)     NOT NULL,
    detected_at     TIMESTAMPTZ     DEFAULT NOW(),
    details         JSONB           NOT NULL,
    suggested_action TEXT           NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_store_time     ON events (store_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_events_store_visitor  ON events (store_id, visitor_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_events_store_type_time ON events (store_id, event_type, timestamp);
CREATE INDEX IF NOT EXISTS idx_sessions_store_time   ON visitor_sessions (store_id, entry_time);
CREATE INDEX IF NOT EXISTS idx_sessions_funnel       ON visitor_sessions (store_id, is_staff, reached_billing, made_purchase);
CREATE INDEX IF NOT EXISTS idx_pos_store_time        ON pos_transactions (store_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_anomalies_store_time  ON anomalies (store_id, detected_at DESC);
"""

# ── Seed data ─────────────────────────────────────────────────────────────────
# Use Python datetime.time objects — NOT SQL string casts like $4::TIME.
# Passing native Python types avoids asyncpg type-inference failures that
# silently roll back parameterised INSERT statements inside transactions.

CANONICAL_STORES = [
    ("store_001", "Koramangala Flagship",  "Bangalore", dtime(9,  0), dtime(21, 0)),
    ("store_002", "Indiranagar Express",   "Bangalore", dtime(10, 0), dtime(22, 0)),
    ("store_003", "Bandra Galleria",       "Mumbai",    dtime(9,  30), dtime(21, 30)),
    ("store_004", "Connaught Place Hub",   "Delhi",     dtime(10, 0), dtime(22, 0)),
    ("store_005", "Park Street Boutique",  "Kolkata",   dtime(9,  0), dtime(21, 0)),
]

_SEED_SQL = """
INSERT INTO stores (store_id, store_name, city, open_time, close_time, layout)
VALUES ($1, $2, $3, $4, $5, $6)
ON CONFLICT (store_id) DO UPDATE
    SET store_name = EXCLUDED.store_name,
        city       = EXCLUDED.city,
        open_time  = EXCLUDED.open_time,
        close_time = EXCLUDED.close_time
"""

# Keep the public alias so api/seed.py can import it
SCHEMA_SQL = _SCHEMA_SQL
SEED_STORES_SQL = _SEED_SQL


# ── Internal helpers ──────────────────────────────────────────────────────────

async def _run_schema(conn: asyncpg.Connection) -> None:
    """Create all tables and indexes (idempotent)."""
    await conn.execute(_SCHEMA_SQL)
    logger.info("Schema applied (CREATE TABLE IF NOT EXISTS).")


async def _run_seed(conn: asyncpg.Connection) -> None:
    """Upsert all canonical stores (idempotent).

    Passes Python datetime.time objects as $4/$5 — asyncpg maps them
    directly to PostgreSQL TIME without requiring a SQL type cast.
    """
    empty_layout = json.dumps({})
    for sid, name, city, open_t, close_t in CANONICAL_STORES:
        await conn.execute(_SEED_SQL, sid, name, city, open_t, close_t, empty_layout)
        logger.info("  store seeded: %s — %s", sid, name)
    count = await conn.fetchval("SELECT COUNT(*) FROM stores")
    logger.info("Stores table now contains %d rows.", count)


async def _verify_stores(conn: asyncpg.Connection) -> int:
    """Return count of canonical stores present in the stores table."""
    ids = [s[0] for s in CANONICAL_STORES]
    count = await conn.fetchval(
        "SELECT COUNT(*) FROM stores WHERE store_id = ANY($1::text[])", ids
    )
    return int(count or 0)


# ── Pool initialisation ───────────────────────────────────────────────────────

async def init_db() -> None:
    """Create pool, create schema, seed stores.

    Schema creation and store seeding are in SEPARATE transactions so a seed
    failure can never roll back the DDL, and vice-versa.

    Advisory lock 42 serialises concurrent uvicorn workers.
    """
    global _pool
    dsn = _get_dsn()

    # Log which database we're connecting to (critical for debugging Render)
    safe_dsn = dsn.split("@")[-1] if "@" in dsn else dsn  # hide credentials
    logger.info("Connecting to PostgreSQL: %s", safe_dsn)

    _pool = await asyncpg.create_pool(dsn, min_size=2, max_size=10)

    async with _pool.acquire() as conn:
        # ── Log DB identity ────────────────────────────────────────────────
        db_name = await conn.fetchval("SELECT current_database()")
        schema   = await conn.fetchval("SELECT current_schema()")
        logger.info("Connected — database=%s  schema=%s", db_name, schema)

        # ── Advisory lock: only one worker runs DDL + seed ─────────────────
        acquired = await conn.fetchval("SELECT pg_try_advisory_lock(42)")
        if acquired:
            try:
                logger.info("Advisory lock 42 acquired.")

                # Transaction 1: schema (DDL)
                async with conn.transaction():
                    await _run_schema(conn)

                # Transaction 2: seed (DML) — separate so DDL is never rolled back
                async with conn.transaction():
                    await _run_seed(conn)

            except Exception as exc:
                logger.error("init_db failed: %s", exc, exc_info=True)
                raise
            finally:
                await conn.execute("SELECT pg_advisory_unlock(42)")
                logger.info("Advisory lock 42 released.")
        else:
            logger.info("Advisory lock 42 held by another worker — waiting for schema/seed.")
            import asyncio
            await asyncio.sleep(2)

        # ── Verify stores exist regardless of which path we took ───────────
        present = await _verify_stores(conn)
        total   = len(CANONICAL_STORES)
        if present < total:
            logger.warning(
                "Only %d/%d canonical stores found — running emergency seed.", present, total
            )
            async with conn.transaction():
                await _run_seed(conn)
            present = await _verify_stores(conn)

        if present < total:
            raise RuntimeError(
                f"STARTUP FAILURE: stores table has {present}/{total} canonical stores. "
                "Ingestion will fail. Check DB connectivity and permissions."
            )

        logger.info(
            "Startup OK — database=%s  schema=%s  stores=%d/%d",
            db_name, schema, present, total,
        )


async def close_db() -> None:
    """Close the connection pool."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def get_pool() -> asyncpg.Pool:
    """Return the active connection pool (initialises on first call)."""
    if _pool is None:
        await init_db()
    return _pool


@asynccontextmanager
async def get_connection() -> AsyncGenerator[asyncpg.Connection, None]:
    """Acquire a connection from the pool."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        yield conn
