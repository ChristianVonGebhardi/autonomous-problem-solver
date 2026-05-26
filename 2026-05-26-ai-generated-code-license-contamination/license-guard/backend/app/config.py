from pydantic_settings import BaseSettings
from typing import List
import os


class Settings(BaseSettings):
    # API
    api_secret_key: str = "dev-secret-key-change-in-production"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    
    # Database
    database_url: str = "postgresql://licenseguard:licenseguard@localhost:5432/licenseguard"
    
    # Redis
    redis_url: str = "redis://localhost:6379/0"
    
    # OpenAI
    openai_api_key: str = ""
    
    # Detection
    similarity_threshold: float = 0.75
    minhash_num_perm: int = 128
    embedding_model: str = "all-MiniLM-L6-v2"
    
    # CORS
    cors_origins: str = "http://localhost:3000,http://localhost:5173"
    
    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.cors_origins.split(",")]
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()