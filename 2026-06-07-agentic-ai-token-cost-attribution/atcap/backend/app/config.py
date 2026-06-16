from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite+aiosqlite:///./atcap.db"
    REDIS_URL: Optional[str] = None
    SECRET_KEY: str = "dev-secret-change-in-production"
    ENVIRONMENT: str = "development"

    # Integrations
    SLACK_WEBHOOK_URL: Optional[str] = None
    GITHUB_TOKEN: Optional[str] = None
    GITHUB_ORG: Optional[str] = None
    JIRA_BASE_URL: Optional[str] = None
    JIRA_TOKEN: Optional[str] = None
    JIRA_PROJECT_KEY: Optional[str] = None

    # Alert defaults
    DEFAULT_BUDGET_ALERT_THRESHOLD_PCT: float = 80.0

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()