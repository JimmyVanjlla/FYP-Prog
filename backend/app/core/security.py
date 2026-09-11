"""
Password hashing and JWT issuance/verification.

Implements NFR-Security: passwords are stored exclusively as salted bcrypt
hashes, and every authenticated request carries a JWT rather than a session
cookie/raw credentials.
"""
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    return _pwd_context.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return _pwd_context.verify(plain_password, password_hash)


def create_access_token(*, subject: str, role: str) -> str:
    """subject is the user_id (as a string); role is embedded so the client
    can route by role without a second lookup, and so require_role() can
    check it without hitting the DB on every request."""
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": subject, "role": role, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """Raises jose.JWTError if the token is invalid or expired — callers
    (see app/deps.py) are responsible for turning that into a 401."""
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


__all__ = [
    "hash_password",
    "verify_password",
    "create_access_token",
    "decode_access_token",
    "JWTError",
]
