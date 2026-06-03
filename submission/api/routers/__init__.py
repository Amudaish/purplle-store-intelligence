"""Routers package."""

from api.routers.ingest import router as ingest_router
from api.routers.metrics import router as metrics_router
from api.routers.funnel import router as funnel_router
from api.routers.heatmap import router as heatmap_router
from api.routers.anomalies import router as anomalies_router
from api.routers.health import router as health_router

__all__ = [
    "ingest_router",
    "metrics_router",
    "funnel_router",
    "heatmap_router",
    "anomalies_router",
    "health_router",
]
