"""
FastAPI application factory — entry-point for the Store Intelligence API.

Lifecycle
---------
startup  : initialise PostgreSQL pool, create schema, seed stores, connect Redis
shutdown : close pool and Redis connection

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
from database import close_db, get_pool, init_db
from middleware import StructuredLoggingMiddleware
from routers import (
    anomalies_router,
    funnel_router,
    health_router,
    heatmap_router,
    ingest_router,
    metrics_router,
)

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
)
logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise and clean up resources on startup/shutdown."""
    logger.info("Starting Store Intelligence API", version="1.0.0")

    # ── Database ───────────────────────────────────────────────────────────────
    # init_db() reads DATABASE_URL from os.environ directly, creates schema,
    # seeds all 5 canonical stores, and raises RuntimeError if seeding fails.
    await init_db()
    logger.info("Database ready.")

    # ── Redis (optional) ───────────────────────────────────────────────────────
    settings = get_settings()
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
        logger.warning("Redis unavailable — real-time stream disabled", error=str(exc))

    yield

    logger.info("Shutting down.")
    await close_db()
    if getattr(app.state, "redis", None):
        await app.state.redis.close()
    logger.info("Shutdown complete.")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Store Intelligence API",
        description="End-to-end retail analytics API.",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(StructuredLoggingMiddleware)

    app.include_router(health_router)
    app.include_router(ingest_router)
    app.include_router(metrics_router)
    app.include_router(funnel_router)
    app.include_router(heatmap_router)
    app.include_router(anomalies_router)

    return app


app = create_app()
