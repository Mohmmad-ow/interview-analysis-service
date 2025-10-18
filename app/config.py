from pydantic_settings import BaseSettings
from typing import List, Optional
import secrets


class Settings(BaseSettings):
    """Application configuration settings."""

    # API Configuration
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Interview Analysis Microservice"

    # Security
    SECRET_KEY: str = secrets.token_urlsafe(32)
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000"]

    # Database
    MYSQL_HOST: str = "localhost"
    MYSQL_USER: str = "interview_service"
    MYSQL_PASSWORD: str = "password"
    MYSQL_DATABASE: str = "interview_audit"
    MYSQL_PORT: int = 3306

    # Redis
    REDIS_URL: str = "redis://localhost:6379"
    REDIS_RATE_LIMIT_DB: int = 0

    # AI Services
    WHISPER_MODEL: str = "base"
    GEMINI_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None

    # Rate Limiting
    DEFAULT_RATE_LIMIT_MINUTE: int = 5
    DEFAULT_RATE_LIMIT_HOUR: int = 50

    # Application
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"
        case_sensitive = True


# Create global settings instance
settings = Settings()
