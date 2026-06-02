from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://flaky:flaky123@localhost:5432/flaky_tests"
    redis_url: str = "redis://localhost:6379"

    # OpenAI
    openai_api_key: Optional[str] = None
    llm_model: str = "gpt-4o"
    llm_max_tokens: int = 2048
    mock_llm: bool = True

    # GitHub
    github_token: Optional[str] = None
    github_app_id: Optional[str] = None
    mock_github: bool = True

    # Workers
    worker_poll_interval: int = 5
    fix_worker_poll_interval: int = 10

    # Flakiness Detection
    min_runs_for_detection: int = 3
    flakiness_threshold: float = 0.3
    confidence_threshold: float = 0.6

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]


settings = Settings()