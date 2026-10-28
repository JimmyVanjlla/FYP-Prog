"""Module 1 business logic, kept out of the router per Ch4's maintainability
NFR ("modular backend structure with separated routers, services, and
database model layers")."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.models.audit import AuditLog
from app.models.roles import Role
from app.models.user import User
from app.schemas.user import UserRegister

# Roles that can't freely self-register once one already exists — see
# register_user_self_service below. Restaurant Owner/Manager hold the most
# privileged, system-wide access (RBAC-wise equal to or above everyone
# else), so an open /auth/register for them would let anyone grant
# themselves manager-level access with no authorization check at all.
_PRIVILEGED_ROLES = {Role.RESTAURANT_OWNER, Role.RESTAURANT_MANAGER}


class DuplicateEmailError(Exception):
    """FR1.6."""


class InvalidCredentialsError(Exception):
    """FR1.7 — deliberately doesn't say which of email/password was wrong."""


class PrivilegedRoleAlreadyProvisionedError(Exception):
    """Raised by register_user_self_service when someone tries to
    self-register as Restaurant Owner/Manager and one already exists."""


def register_user(db: Session, data: UserRegister) -> User:
    """The core creation logic, with no role restriction — used directly by
    the Manager-only POST /users endpoint (app/routers/users.py), and by
    register_user_self_service below once it's decided the role is allowed."""
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


def register_user_self_service(db: Session, data: UserRegister) -> User:
    """FR1.1's open /auth/register, with one guard: self-registering as
    Restaurant Owner or Restaurant Manager is only allowed when no account
    with that exact role exists yet (the system's bootstrap window — the
    very first Owner/Manager account has to come from somewhere with no
    Manager yet available to provision it). Once one exists, further
    Owner/Manager accounts must come from an existing Manager via
    POST /users, same as any other staff account they create for someone
    else."""
    if data.role in _PRIVILEGED_ROLES:
        already_exists = db.scalar(select(User).where(User.role == data.role.value).limit(1))
        if already_exists is not None:
            raise PrivilegedRoleAlreadyProvisionedError
    return register_user(db, data)


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
