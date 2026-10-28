"""
Login brute-force protection: a fixed-window counter in Redis, keyed per
email (not per IP — this is a staff-facing internal tool behind no load
balancer/proxy guaranteed to forward a real client IP, and the thing worth
protecting is a given account, not a given network address).

NFR-Security: previously /auth/login had no limit on attempts at all.
"""
import time

from fastapi import HTTPException, status
from redis import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)

_redis_client: Redis | None = None

# Short-lived circuit breaker: if Redis was unreachable a moment ago, don't
# retry-and-wait-out-the-connect-timeout on every single subsequent login
# call (e.g. a test suite making ~100 login calls against a Redis-less
# environment would otherwise pay a multi-second connect timeout each time).
_unavailable_until: float = 0.0
_COOLDOWN_SECONDS = 10


def _get_redis() -> Redis:
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = Redis.from_url(
            settings.redis_url, decode_responses=True, socket_connect_timeout=0.5, socket_timeout=0.5
        )
    return _redis_client


def check_login_rate_limit(email: str) -> None:
    """Raises 429 if this email has exceeded the configured attempt count
    within the current window. Fails open (logs and allows the request)
    if Redis itself is unreachable — a down rate limiter shouldn't take
    the login endpoint down with it."""
    global _unavailable_until
    if time.monotonic() < _unavailable_until:
        return

    settings = get_settings()
    key = f"login_attempts:{email.strip().lower()}"
    try:
        client = _get_redis()
        count = client.incr(key)
        if count == 1:
            client.expire(key, settings.login_rate_limit_window_seconds)
        if count > settings.login_rate_limit_attempts:
            ttl = client.ttl(key)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    "Too many login attempts for this account. "
                    f"Try again in {max(ttl, 1)} seconds."
                ),
            )
    except RedisError:
        _unavailable_until = time.monotonic() + _COOLDOWN_SECONDS
        logger.warning("Rate limiter unreachable (Redis error) — allowing login request through.")


def reset_login_rate_limit(email: str) -> None:
    """Called on a successful login so a genuine user isn't penalized for
    earlier mistyped attempts once they do get it right."""
    if time.monotonic() < _unavailable_until:
        return
    try:
        client = _get_redis()
        client.delete(f"login_attempts:{email.strip().lower()}")
    except RedisError:
        pass


__all__ = ["check_login_rate_limit", "reset_login_rate_limit"]
