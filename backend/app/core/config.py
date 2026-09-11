"""
Application settings, loaded from environment variables (.env in local dev).

See ../../.env.example for the full list of variables this reads and what
each one is for.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Postgres connection string, e.g. from a Supabase project:
    # postgresql+psycopg://user:password@host:5432/postgres
    database_url: str = "sqlite:///./dev.db"

    # Redis connection string (not used until the Demand Forecasting sprint
    # wires up Celery, but captured now so it's a drop-in later), e.g. from
    # Upstash: rediss://default:password@host:6379
    redis_url: str = "redis://localhost:6379/0"

    # JWT signing secret. MUST be overridden via .env outside of local dev.
    jwt_secret: str = "dev-only-insecure-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24  # 24h, generous for a staff-facing internal tool

    environment: str = "development"

    # Firebase Cloud Messaging — FR5.4 / Ch4 §4.1 "External & Invoked
    # Services". Unset by default: see app/services/notifications.py, which
    # falls back to storing Notification rows as queued_for_retry (an
    # honest status, not a fake "sent") until a real service account is
    # provided here.
    fcm_credentials_path: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
