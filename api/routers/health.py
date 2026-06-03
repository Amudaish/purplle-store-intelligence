"""
GET /health — service health check endpoint.

Returns:
- status        : "ok" | "degraded" | "error"
- db_status     : "ok" | "error"
- redis_status  : "ok" | "unavailable"
- last_event_at : ISO timestamp of the most recent event ingested
- stale_feed    : true if last_event_at is older than STALE_THRESHOLD minutes
- uptime_s      : seconds since startup
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from config import get_settings
from database import get_pool

router = APIRouter(tags=["health"])

_STARTUP_TIME = time.monotonic()


@router.get(
    "/health",
    summary="Service health check",
    description=(
        "Returns the health of the API, database, and Redis connections. "
        "Includes a STALE_FEED warning if no events have been ingested "
        "in the last 10 minutes."
    ),
)
async def health_check(request: Request) -> JSONResponse:
    settings = get_settings()
    uptime_s = round(time.monotonic() - _STARTUP_TIME, 1)
    now = datetime.now(tz=timezone.utc)

    # ── Database ping ──────────────────────────────────────────────────
    db_status = "ok"
    last_event_at: str | None = None
    stale_feed = False

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT MAX(created_at) AS last_event FROM events"
            )
            if row and row["last_event"]:
                last_event_dt: datetime = row["last_event"]
                if last_event_dt.tzinfo is None:
                    last_event_dt = last_event_dt.replace(tzinfo=timezone.utc)
                last_event_at = last_event_dt.isoformat()
                age = (now - last_event_dt).total_seconds() / 60
                stale_feed = age > settings.stale_feed_threshold_minutes
    except Exception as exc:
        db_status = f"error: {exc}"

    # ── Redis ping ─────────────────────────────────────────────────────
    redis_status = "unavailable"
    redis = getattr(request.app.state, "redis", None)
    if redis is not None:
        try:
            await redis.ping()
            redis_status = "ok"
        except Exception as exc:
            redis_status = f"error: {exc}"

    # ── Overall health state ───────────────────────────────────────────
    # "error"    → critical dependency (DB or Redis) is down  → HTTP 503
    # "degraded" → dependencies ok, but event feed is stale   → HTTP 200
    # "ok"       → everything healthy                         → HTTP 200
    #
    # HTTP 503 is reserved for machine-readable failure signals
    # (load balancers, k8s probes). Stale-feed is a business-level
    # warning surfaced via the JSON body, not the status code.
    critical_failure = not db_status.startswith("ok") or (
        redis is not None and not redis_status.startswith("ok")
    )
    if critical_failure:
        overall = "error"
    elif stale_feed:
        overall = "degraded"
    else:
        overall = "ok"

    body = {
        "status": overall,
        "db_status": db_status,
        "redis_status": redis_status,
        "last_event_at": last_event_at,
        "stale_feed": stale_feed,
        "uptime_s": uptime_s,
    }
    if stale_feed:
        body["warning"] = "STALE_FEED"

    http_status = 503 if overall == "error" else 200
    return JSONResponse(content=body, status_code=http_status)
