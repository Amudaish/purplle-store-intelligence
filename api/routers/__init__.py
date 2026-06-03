"""Routers package."""

from routers.ingest import router as ingest_router
from routers.metrics import router as metrics_router
from routers.funnel import router as funnel_router
from routers.heatmap import router as heatmap_router
from routers.anomalies import router as anomalies_router
from routers.health import router as health_router

__all__ = [
    "ingest_router",
    "metrics_router",
    "funnel_router",
    "heatmap_router",
    "anomalies_router",
    "health_router",
]
