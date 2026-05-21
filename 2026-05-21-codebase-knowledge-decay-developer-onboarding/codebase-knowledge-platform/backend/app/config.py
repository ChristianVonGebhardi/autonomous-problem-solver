from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    # LLM
    openai_api_key: Optional[str] = Field(default=None, env="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o", env="OPENAI_MODEL")
    use_ollama: bool = Field(default=False, env="USE_OLLAMA")
    ollama_base_url: str = Field(default="http://localhost:11434", env="OLLAMA_BASE_URL")
    ollama_model: str = Field(default="codellama", env="OLLAMA_MODEL")

    # GitHub
    github_token: Optional[str] = Field(default=None, env="GITHUB_TOKEN")

    # Neo4j
    neo4j_uri: str = Field(default="bolt://localhost:7687", env="NEO4J_URI")
    neo4j_user: str = Field(default="neo4j", env="NEO4J_USER")
    neo4j_password: str = Field(default="password123", env="NEO4J_PASSWORD")

    # Qdrant
    qdrant_host: str = Field(default="localhost", env="QDRANT_HOST")
    qdrant_port: int = Field(default=6333, env="QDRANT_PORT")

    # Postgres
    database_url: str = Field(
        default="postgresql+asyncpg://codeknow:codeknow@localhost:5432/codeknow",
        env="DATABASE_URL",
    )
    postgres_url: str = Field(
        default="postgresql://codeknow:codeknow@localhost:5432/codeknow",
        env="POSTGRES_URL",
    )

    # Redis / Celery
    redis_url: str = Field(default="redis://localhost:6379/0", env="REDIS_URL")
    celery_broker_url: str = Field(default="redis://localhost:6379/1", env="CELERY_BROKER_URL")
    celery_result_backend: str = Field(default="redis://localhost:6379/2", env="CELERY_RESULT_BACKEND")

    # Embeddings
    embedding_model: str = Field(default="all-MiniLM-L6-v2", env="EMBEDDING_MODEL")
    embedding_dimension: int = Field(default=384, env="EMBEDDING_DIMENSION")

    # API
    api_secret_key: str = Field(default="dev-secret-key", env="API_SECRET_KEY")
    cors_origins: str = Field(default="http://localhost:3000", env="CORS_ORIGINS")

    # Ingestion
    max_file_size_kb: int = Field(default=500, env="MAX_FILE_SIZE_KB")
    chunk_size: int = Field(default=512, env="CHUNK_SIZE")
    chunk_overlap: int = Field(default=64, env="CHUNK_OVERLAP")
    max_commits_per_ingest: int = Field(default=500, env="MAX_COMMITS_PER_INGEST")

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()