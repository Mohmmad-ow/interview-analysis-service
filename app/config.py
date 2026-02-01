from pydantic_settings import BaseSettings, SettingsConfigDict
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
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "https://localhost:8021",
        "http://127.0.0.1:8000",
    ]

    # Database
    MYSQL_HOST: str = "localhost"
    MYSQL_USER: str = "root"
    MYSQL_PASSWORD: str = "password"
    MYSQL_DATABASE: str = "interview-analysis-database"
    MYSQL_PORT: int = 3306

    # Redis
    REDIS_URL: str = "localhost"
    REDIS_RATE_LIMIT_DB: int = 0
    REDIS_CACHE_DB: int = 1
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None

    # Rate Limiting
    # Standard limits
    STANDARD_RATE_LIMIT_MINUTE: int = 5
    STANDARD_RATE_LIMIT_HOUR: int = 50

    # Premium limits
    PREMIUM_RATE_LIMIT_MINUTE: int = 20
    PREMIUM_RATE_LIMIT_HOUR: int = 200

    # Admin limits
    ADMIN_RATE_LIMIT_MINUTE: int = 100
    ADMIN_RATE_LIMIT_HOUR: int = 1000

    # AI Services

    # Whisper Configuration
    WHISPER_MODEL_SIZE: str = "tiny"  # tiny, base, small, medium, large
    WHISPER_DEVICE: str = "auto"  # auto, cpu, cuda
    MAX_AUDIO_DURATION: int = 3600  # Max 1 hour audio
    SUPPORTED_LANGUAGES: List[str] = ["en", "ar"]

    # OpenAI / Gemini API Keys
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-2.5-flash"

    # Application
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # Pydantic V2 style config
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
    )


# Create global settings instance
settings = Settings()
