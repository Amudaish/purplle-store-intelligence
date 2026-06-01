"""
PROMPT:
Generate a pytest conftest.py for an async FastAPI application backed by
asyncpg (PostgreSQL) and Redis.  Provide:
- An async test client using httpx.AsyncClient with the FastAPI app
- A DB fixture that creates all tables, runs tests, then drops them
- Factory fixtures for sample events, stores, and POS transactions
- A fixture that pre-populates the DB with a small dataset

CHANGES MADE:
- Used pytest-asyncio with asyncio_mode="auto"
- Replaced SQLAlchemy test DB with asyncpg directly (matches api/database.py)
- Added store_id fixture seeding the stores table before tests
- Created event_factory callable fixture for flexible event generation
- Mock Redis via fakeredis.aioredis for isolated test runs
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator, Callable

import asyncpg
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# ── Pytest configuration ───────────────────────────────────────────────────────
# Set in pytest.ini or pyproject.toml:  asyncio_mode = "auto"


_TEST_DSN = "postgresql://store_intel:store_intel_pass@localhost:5432/store_intelligence_test"
_TEST_STORE_ID = "store_001"


# ── Event loop ─────────────────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def event_loop():
    """Session-scoped event loop for all async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ── Database ───────────────────────────────────────────────────────────────────
@pytest_asyncio.fixture(scope="session")
async def db_pool() -> AsyncGenerator[asyncpg.Pool, None]:
    """Create a connection pool to the test database and initialise schema."""
    from api.database import SCHEMA_SQL

    pool = await asyncpg.create_pool(_TEST_DSN, min_size=2, max_size=5)
    async with pool.acquire() as conn:
        await conn.execute(SCHEMA_SQL)
    yield pool
    # Teardown — drop all test data
    async with pool.acquire() as conn:
        await conn.execute(
            """
            TRUNCATE anomalies, pos_transactions, visitor_sessions, events, stores
            CASCADE
            """
        )
    await pool.close()


@pytest_asyncio.fixture(autouse=True)
async def clean_tables(db_pool: asyncpg.Pool):
    """Truncate tables between each test for isolation."""
    yield
    async with db_pool.acquire() as conn:
        await conn.execute(
            "TRUNCATE anomalies, pos_transactions, visitor_sessions, events CASCADE"
        )


@pytest_asyncio.fixture
async def seed_store(db_pool: asyncpg.Pool):
    """Insert the test store into the stores table."""
    from data.store_layout import _LAYOUT  # type: ignore  # loaded below
    import json as _json
    layout_path = __import__("pathlib").Path("data/store_layout.json")
    layout = _json.loads(layout_path.read_text()) if layout_path.exists() else {}
    store_data = layout.get("stores", {}).get(_TEST_STORE_ID, {})

    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO stores (store_id, store_name, city, open_time, close_time, layout)
            VALUES ($1, $2, $3, '09:00'::TIME, '21:00'::TIME, $4)
            ON CONFLICT (store_id) DO NOTHING
            """,
            _TEST_STORE_ID,
            store_data.get("name", "Test Store"),
            store_data.get("city", "TestCity"),
            _json.dumps(store_data),
        )
    return _TEST_STORE_ID


# ── Mock Redis ─────────────────────────────────────────────────────────────────
@pytest_asyncio.fixture
async def mock_redis():
    """Fake Redis using fakeredis.aioredis (no real Redis needed in tests)."""
    try:
        import fakeredis.aioredis as fakeredis  # type: ignore
        r = fakeredis.FakeRedis()
        yield r
        await r.aclose()
    except ImportError:
        # Fallback: no Redis in tests
        yield None


# ── FastAPI test client ────────────────────────────────────────────────────────
@pytest_asyncio.fixture
async def client(db_pool: asyncpg.Pool, mock_redis, seed_store) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTPX test client wired to the FastAPI app."""
    from api.main import app
    import api.database as db_module

    # Patch the module-level pool with our test pool
    original_pool = db_module._pool
    db_module._pool = db_pool
    app.state.redis = mock_redis

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as ac:
        yield ac

    db_module._pool = original_pool


# ── Event factory ──────────────────────────────────────────────────────────────
@pytest.fixture
def make_event() -> Callable[..., dict]:
    """
    Factory fixture — returns a function that creates a valid event dict.

    Usage:  event = make_event(event_type="ENTRY")
    """
    def _factory(
        event_type: str = "ENTRY",
        store_id: str = _TEST_STORE_ID,
        camera_id: str = "cam_entry",
        visitor_id: str | None = None,
        zone_id: str | None = None,
        dwell_ms: int | None = None,
        is_staff: bool = False,
        confidence: float = 0.90,
        ts: datetime | None = None,
        metadata: dict | None = None,
    ) -> dict:
        return {
            "event_id": str(uuid.uuid4()),
            "store_id": store_id,
            "camera_id": camera_id,
            "visitor_id": visitor_id or str(uuid.uuid4()),
            "event_type": event_type,
            "timestamp": (ts or datetime.now(tz=timezone.utc)).isoformat(),
            "zone_id": zone_id,
            "dwell_ms": dwell_ms,
            "is_staff": is_staff,
            "confidence": confidence,
            "metadata": metadata or {},
        }
    return _factory


@pytest.fixture
def make_batch(make_event) -> Callable[..., dict]:
    """Factory for a BatchIngestRequest payload."""
    def _factory(events: list[dict]) -> dict:
        return {"events": events}
    return _factory


# ── POS transaction factory ────────────────────────────────────────────────────
@pytest.fixture
def make_pos_transaction() -> Callable[..., dict]:
    def _factory(
        store_id: str = _TEST_STORE_ID,
        basket_value: float = 999.0,
        ts: datetime | None = None,
    ) -> dict:
        return {
            "transaction_id": str(uuid.uuid4()),
            "store_id": store_id,
            "timestamp": (ts or datetime.now(tz=timezone.utc)).isoformat(),
            "basket_value_inr": basket_value,
        }
    return _factory
