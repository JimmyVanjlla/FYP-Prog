"""Module 1 business logic, kept out of the router per Ch4's maintainability
NFR ("modular backend structure with separated routers, services, and
database model layers")."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
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


class WrongCurrentPasswordError(Exception):
    """The current password given when changing a password was incorrect."""


class PublicRegistrationClosedError(Exception):
    """Raised by register_user_self_service when public registration is closed
    and the caller is not creating the very first Manager/Owner account."""


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
        phone_number=data.phone_number,
        address=data.address,
        emergency_contact_name=data.emergency_contact_name,
        emergency_contact_phone=data.emergency_contact_phone,
    )
    db.add(user)
    db.flush()
    _log_action(db, user_id=user.user_id, action="register")
    db.commit()
    db.refresh(user)
    return user


def _public_registration_open() -> bool:
    settings = get_settings()
    if settings.public_registration_enabled is not None:
        return settings.public_registration_enabled
    return settings.environment != "production"


def register_user_self_service(db: Session, data: UserRegister) -> User:
    """FR1.1's /auth/register. Two guards.

    1. Where public registration is closed (production, by default), the only
       account anyone can create for themselves is the very first one, and it
       must be a Restaurant Manager or Owner, since only they can create the
       rest (POST /users). Without that, anyone who found the app could make
       themselves a Kitchen or Procurement account.
    2. Self-registering as Restaurant Owner or Restaurant Manager is only
       allowed when no account with that exact role exists yet (the
       bootstrap window); further ones come from an existing Manager or
       Owner via POST /users."""
    if not _public_registration_open():
        nobody_exists_yet = db.scalar(select(User).limit(1)) is None
        if not (nobody_exists_yet and data.role in _PRIVILEGED_ROLES):
            raise PublicRegistrationClosedError
    if data.role in _PRIVILEGED_ROLES:
        already_exists = db.scalar(select(User).where(User.role == data.role.value).limit(1))
        if already_exists is not None:
            raise PrivilegedRoleAlreadyProvisionedError
    return register_user(db, data)


def change_password(db: Session, user: User, *, current_password: str, new_password: str) -> None:
    """A person changing their own password. Requires the current one, so a
    phone left unlocked cannot be used to take over the account."""
    if not verify_password(current_password, user.password_hash):
        raise WrongCurrentPasswordError
    user.password_hash = hash_password(new_password)
    db.commit()  # the request itself is already in the audit trail (deps.get_current_user)


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
