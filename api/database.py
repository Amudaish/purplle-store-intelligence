"""PostgreSQL database connection and schema management."""

import asyncpg
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from api.config import get_settings

# Module-level connection pool
_pool: asyncpg.Pool | None = None

SCHEMA_SQL = """
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

-- Indexes
CREATE INDEX IF NOT EXISTS idx_events_store_time ON events (store_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_events_store_visitor ON events (store_id, visitor_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_events_store_type_time ON events (store_id, event_type, timestamp);
CREATE INDEX IF NOT EXISTS idx_sessions_store_time ON visitor_sessions (store_id, entry_time);
CREATE INDEX IF NOT EXISTS idx_sessions_funnel ON visitor_sessions (store_id, is_staff, reached_billing, made_purchase);
CREATE INDEX IF NOT EXISTS idx_pos_store_time ON pos_transactions (store_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_anomalies_store_time ON anomalies (store_id, detected_at DESC);
"""


def _get_dsn() -> str:
    """Convert SQLAlchemy URL to asyncpg DSN."""
    url = get_settings().database_url
    return url.replace("postgresql+asyncpg://", "postgresql://")


async def init_db() -> None:
    """Initialize the connection pool and create schema.

    Uses a PostgreSQL session-level advisory lock (key 42) to serialise
    schema creation across concurrent uvicorn workers.  Only the worker
    that wins the lock actually runs the DDL; every other worker exits
    immediately (the schema already exists or is being created).
    """
    global _pool
    dsn = _get_dsn()
    _pool = await asyncpg.create_pool(dsn, min_size=2, max_size=10)
    async with _pool.acquire() as conn:
        # Try to acquire an exclusive session-level advisory lock.
        # Returns True only for the one worker that wins the race.
        acquired = await conn.fetchval("SELECT pg_try_advisory_lock(42)")
        if not acquired:
            # Another worker is already running (or has just finished)
            # the schema migration — nothing to do here.
            return
        try:
            async with conn.transaction():
                await conn.execute(SCHEMA_SQL)
        finally:
            # Release immediately so the lock doesn't linger on the
            # connection while it sits idle in the pool.
            await conn.execute("SELECT pg_advisory_unlock(42)")


async def close_db() -> None:
    """Close the connection pool."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def get_pool() -> asyncpg.Pool:
    """Return the active connection pool."""
    if _pool is None:
        await init_db()
    return _pool


@asynccontextmanager
async def get_connection() -> AsyncGenerator[asyncpg.Connection, None]:
    """Acquire a connection from the pool."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        yield conn
