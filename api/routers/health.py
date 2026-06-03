"""GET /health — service health check endpoint."""

from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from config import get_settings
from database import CANONICAL_STORES, get_pool

router = APIRouter(tags=["health"])

_STARTUP_TIME = time.monotonic()
_EXPECTED_STORE_IDS = [s[0] for s in CANONICAL_STORES]


@router.get("/health", summary="Service health check")
async def health_check(request: Request) -> JSONResponse:
    settings = get_settings()
    uptime_s = round(time.monotonic() - _STARTUP_TIME, 1)

    db_status = "ok"
    db_name: str | None = None
    schema_name: str | None = None
    stores_seeded = 0
    stores_ok = False
    missing_stores: list[str] = []
    last_event_at: str | None = None
    stale_feed = False

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            # DB identity — proves both endpoints hit the same database
            db_name   = await conn.fetchval("SELECT current_database()")
            schema_name = await conn.fetchval("SELECT current_schema()")

            # Store presence check
            rows = await conn.fetch("SELECT store_id FROM stores ORDER BY store_id")
            present_ids = {r["store_id"] for r in rows}
            stores_seeded = len(present_ids)
            missing_stores = sorted(set(_EXPECTED_STORE_IDS) - present_ids)
            stores_ok = len(missing_stores) == 0

            # Last event
            row = await conn.fetchrow("SELECT MAX(created_at) AS ts FROM events")
            if row and row["ts"]:
                ts: datetime = row["ts"]
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                last_event_at = ts.isoformat()
                age_min = (datetime.now(tz=timezone.utc) - ts).total_seconds() / 60
                stale_feed = age_min > settings.stale_feed_threshold_minutes
    except Exception as exc:
        db_status = f"error: {exc}"

    # Redis
    redis_status = "unavailable"
    redis = getattr(request.app.state, "redis", None)
    if redis is not None:
        try:
            await redis.ping()
            redis_status = "ok"
        except Exception as exc:
            redis_status = f"error: {exc}"

    critical = not db_status.startswith("ok") or not stores_ok
    overall = "error" if critical else ("degraded" if stale_feed else "ok")

    body: dict = {
        "status": overall,
        "db_status": db_status,
        "db_name": db_name,
        "schema_name": schema_name,
        "redis_status": redis_status,
        "stores_seeded": stores_seeded,
        "stores_ok": stores_ok,
        "last_event_at": last_event_at,
        "stale_feed": stale_feed,
        "uptime_s": uptime_s,
    }
    if missing_stores:
        body["missing_stores"] = missing_stores
    if stale_feed:
        body["warning"] = "STALE_FEED"

    return JSONResponse(content=body, status_code=503 if overall == "error" else 200)
