from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    environment: str = "development"
    log_level: str = "INFO"
    secret_key: str = "change-me"
    api_key: str = "dev-api-key"

    # Database
    database_url: str = "postgresql+asyncpg://lifeadmin:lifeadmin123@localhost:5432/lifeadmin"

    # Redis
    redis_url: str = "redis://localhost:6379"

    # Anthropic
    anthropic_api_key: str = ""

    # Gmail OAuth2
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/ingestion/oauth/callback"
    google_refresh_token: str = ""

    # Notifications
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    notification_email: str = ""

    # Agent tuning
    urgent_days_threshold: int = 2
    overpriced_threshold: float = 5000.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
