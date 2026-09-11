"""Module 1 business logic, kept out of the router per Ch4's maintainability
NFR ("modular backend structure with separated routers, services, and
database model layers")."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.models.audit import AuditLog
from app.models.user import User
from app.schemas.user import UserRegister


class DuplicateEmailError(Exception):
    """FR1.6."""


class InvalidCredentialsError(Exception):
    """FR1.7 — deliberately doesn't say which of email/password was wrong."""


def register_user(db: Session, data: UserRegister) -> User:
    existing = db.scalar(select(User).where(User.email == data.email))
    if existing is not None:
        raise DuplicateEmailError

    user = User(
        name=data.name,
        email=data.email,
        password_hash=hash_password(data.password),
        role=data.role.value,
        is_active=True,
    )
    db.add(user)
    db.flush()
    _log_action(db, user_id=user.user_id, action="register")
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> tuple[str, str]:
    """Returns (access_token, role) on success; raises
    InvalidCredentialsError otherwise (FR1.7 — same error for "no such
    email" and "wrong password")."""
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        raise InvalidCredentialsError

    _log_action(db, user_id=user.user_id, action="login")
    db.commit()
    token = create_access_token(subject=str(user.user_id), role=user.role)
    return token, user.role


def _log_action(db: Session, *, user_id: int, action: str) -> None:
    """FR1.5 — audit trail. See app/models/audit.py for why this table
    exists beyond Ch4's documented 33 entities."""
    db.add(AuditLog(user_id=user_id, action=action))
