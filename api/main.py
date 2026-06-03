"""
FastAPI application factory — entry-point for the Store Intelligence API.

Lifecycle
---------
startup  : initialise PostgreSQL pool, create schema, connect Redis
shutdown : close pool and Redis connection

Middleware
----------
- CORS (all origins — restrict in production)
- StructuredLoggingMiddleware (JSON logs with trace_id)

Routers
-------
- POST /events/ingest
- GET  /stores/{id}/metrics
- GET  /stores/{id}/funnel
- GET  /stores/{id}/heatmap
- GET  /stores/{id}/anomalies
- GET  /health
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from database import close_db, init_db
from middleware import StructuredLoggingMiddleware
from routers import (
    anomalies_router,
    funnel_router,
    health_router,
    heatmap_router,
    ingest_router,
    metrics_router,
)

# ── Logging configuration ──────────────────────────────────────────────────────
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
)
logger = structlog.get_logger(__name__)


# ── Lifespan ───────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise and clean up resources on startup/shutdown."""
    settings = get_settings()
    logger.info("Starting Store Intelligence API", version="1.0.0")

    # Database
    await init_db()
    logger.info("PostgreSQL pool initialised")

    # Redis (optional — API degrades gracefully without it)
    try:
        import redis.asyncio as aioredis  # type: ignore

        redis_client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=False,
        )
        await redis_client.ping()
        app.state.redis = redis_client
        logger.info("Redis connected", url=settings.redis_url)
    except Exception as exc:
        app.state.redis = None
        logger.warning(
            "Redis unavailable — real-time stream publishing disabled",
            error=str(exc),
        )

    yield  # ── application is running ──────────────────────────────────────

    logger.info("Shutting down Store Intelligence API")
    await close_db()
    if getattr(app.state, "redis", None):
        await app.state.redis.close()
    logger.info("Shutdown complete")


# ── Application factory ────────────────────────────────────────────────────────
def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Store Intelligence API",
        description=(
            "End-to-end retail analytics API for Apex Retail. "
            "Processes CCTV event streams into actionable store metrics."
        ),
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ── Middleware ─────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],   # Restrict in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(StructuredLoggingMiddleware)

    # ── Routers ────────────────────────────────────────────────────────────────
    app.include_router(health_router)
    app.include_router(ingest_router)
    app.include_router(metrics_router)
    app.include_router(funnel_router)
    app.include_router(heatmap_router)
    app.include_router(anomalies_router)

    return app


app = create_app()
