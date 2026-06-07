"""Application configuration via environment variables."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str = "postgresql://localhost/drift_detection"

    # LLM explainability (optional)
    openai_api_key: str = ""

    # Drift thresholds
    drift_alert_threshold: float = 0.65
    structural_weight: float = 0.35
    semantic_weight: float = 0.40
    distributional_weight: float = 0.25

    # CUSUM / EWMA
    ewma_alpha: float = 0.3
    cusum_threshold: float = 5.0
    cusum_slack: float = 1.0

    # Worker
    worker_poll_interval: int = 2
    worker_batch_size: int = 10

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # Embedding model
    embedding_model: str = "all-MiniLM-L6-v2"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]


settings = Settings()