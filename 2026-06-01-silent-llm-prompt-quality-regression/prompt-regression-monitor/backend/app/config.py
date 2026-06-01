from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://promptmonitor:promptmonitor@localhost:5432/promptmonitor"
    sync_database_url: str = "postgresql+psycopg2://promptmonitor:promptmonitor@localhost:5432/promptmonitor"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # LLM Provider
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    llm_provider_base_url: str = "https://api.openai.com"
    judge_model: str = "gpt-4o-mini"

    # Security
    secret_key: str = "dev-secret-key-change-in-production"

    # Alerts
    slack_webhook_url: Optional[str] = None
    pagerduty_routing_key: Optional[str] = None
    alert_email: Optional[str] = None

    # Drift detection thresholds
    cusum_threshold: float = 5.0
    cusum_slack: float = 0.5
    mann_whitney_alpha: float = 0.05
    min_samples_for_detection: int = 10
    baseline_window_hours: int = 24
    detection_window_hours: int = 4

    # Scoring
    embedding_model: str = "text-embedding-3-small"
    use_llm_judge: bool = True
    use_embeddings: bool = True
    use_rouge: bool = True

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()