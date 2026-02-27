"""Configuration via pydantic-settings."""

from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "MarketingAutomation-Lite"
    app_env: str = "development"
    secret_key: str = "change-me"
    debug: bool = False

    # Database
    database_url: str = "postgresql+asyncpg://mal:mal_password@localhost:5432/mal_db"
    database_url_sync: str = "postgresql://mal:mal_password@localhost:5432/mal_db"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # SMTP
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_name: str = "MarketingAutomation"
    smtp_from_email: str = "noreply@example.com"
    smtp_use_tls: bool = True

    # Mail backend: smtp | ses
    mail_backend: str = "smtp"

    # AWS (for SES)
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "us-east-1"

    # Celery
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # Auth
    admin_email: str = "admin@example.com"
    admin_password: str = "changeme123"
    jwt_expire_minutes: int = 1440

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
