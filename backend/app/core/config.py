"""
Application settings, loaded from environment variables (.env in local dev).

See ../../.env.example for the full list of variables this reads and what
each one is for.
"""
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The literal default below — never a real secret, just a placeholder that's
# obviously insecure and (being public in this repo) forgeable by anyone who
# reads the source. See Settings._reject_insecure_secret_in_production.
_INSECURE_DEFAULT_JWT_SECRET = "dev-only-insecure-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Postgres connection string, e.g. from a Supabase project:
    # postgresql+psycopg://user:password@host:5432/postgres
    database_url: str = "sqlite:///./dev.db"

    # Redis connection string, e.g. from Redis Cloud:
    # redis://default:password@host:port
    redis_url: str = "redis://localhost:6379/0"

    # JWT signing secret. MUST be overridden via .env outside of local dev —
    # enforced below when environment=="production".
    jwt_secret: str = _INSECURE_DEFAULT_JWT_SECRET
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24  # 24h, generous for a staff-facing internal tool

    environment: str = "development"

    # Comma-separated list of origins allowed to make cross-origin browser
    # requests (e.g. "https://admin.example.com,http://localhost:3000").
    # Empty by default: the Flutter mobile app doesn't send an Origin header
    # and isn't affected either way, so an empty list is the safe default
    # rather than silently allowing everything.
    cors_allowed_origins: str = ""

    # Login rate limiting (app/core/rate_limit.py) — max attempts per email
    # within the window before further attempts are rejected with 429.
    login_rate_limit_attempts: int = 5
    login_rate_limit_window_seconds: int = 900  # 15 minutes

    # Firebase Cloud Messaging — FR5.4 / Ch4 §4.1 "External & Invoked
    # Services". Unset by default: see app/services/notifications.py, which
    # falls back to storing Notification rows as queued_for_retry (an
    # honest status, not a fake "sent") until a real service account is
    # provided here.
    fcm_credentials_path: str | None = None

    @model_validator(mode="after")
    def _reject_insecure_secret_in_production(self) -> "Settings":
        # NFR-Security: a forgeable, publicly-known JWT secret left in place
        # for a production deployment would let anyone mint a valid token
        # for any role. Local dev and the test suite both run with
        # environment="development" (the default), so this never fires for
        # them — only a deployment that explicitly sets ENVIRONMENT=production
        # without also overriding JWT_SECRET.
        if self.environment == "production" and self.jwt_secret == _INSECURE_DEFAULT_JWT_SECRET:
            raise ValueError(
                "JWT_SECRET must be overridden via .env when ENVIRONMENT=production — "
                "the default value is public (it's in this repo's source) and forgeable."
            )
        return self

    @property
    def cors_allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
