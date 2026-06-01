"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings with environment variable loading."""

    # Database
    database_url: str = "postgresql+asyncpg://store_intel:store_intel_pass@localhost:5432/store_intelligence"
    database_url_sync: str = "postgresql://store_intel:store_intel_pass@localhost:5432/store_intelligence"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    log_level: str = "INFO"

    # Tuning
    max_batch_size: int = 500
    pos_match_window_minutes: int = 5
    stale_feed_threshold_minutes: int = 10
    low_confidence_session_threshold: int = 20

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache()
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()
