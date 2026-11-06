import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.roles import Role

_PHONE = re.compile(r"^\+?[0-9][0-9 ()\-]{5,28}[0-9]$")


def _blank_to_none(value: str | None) -> str | None:
    """The app sends an emptied field as "": treat that as "no value"."""
    if value is None:
        return None
    value = value.strip()
    return value or None


class _ContactDetails(BaseModel):
    """The optional contact details a staff account can carry. Shared by
    account creation, the Manager/Owner's edit, and a person's own profile."""

    phone_number: str | None = Field(default=None, max_length=30)
    address: str | None = Field(default=None, max_length=300)
    emergency_contact_name: str | None = Field(default=None, max_length=150)
    emergency_contact_phone: str | None = Field(default=None, max_length=30)

    @field_validator("phone_number", "address", "emergency_contact_name", "emergency_contact_phone", mode="before")
    @classmethod
    def _tidy(cls, value):
        return _blank_to_none(value) if isinstance(value, str) or value is None else value

    @field_validator("phone_number", "emergency_contact_phone")
    @classmethod
    def _looks_like_a_phone_number(cls, value: str | None) -> str | None:
        if value is not None and not _PHONE.match(value):
            raise ValueError("Enter a valid phone number, for example +60 12-345 6789.")
        return value


class UserRegister(_ContactDetails):
    """FR1.1 — name, email, and password are the only inputs required; the
    contact details are optional."""

    name: str = Field(min_length=1, max_length=150)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: Role


class UserLogin(BaseModel):
    """FR1.2 — no role field: the role comes back embedded in the issued
    JWT, never selected by the client (Ch4 §4.4.1 auth UI principle)."""

    email: EmailStr
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: int
    name: str
    email: EmailStr
    role: Role
    is_active: bool
    phone_number: str | None = None
    address: str | None = None
    emergency_contact_name: str | None = None
    emergency_contact_phone: str | None = None
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: Role


class UserUpdate(_ContactDetails):
    """FR1.4 — a Restaurant Manager or Owner updates a staff account: reassign
    role, activate/deactivate, correct the name or the contact details. All
    fields optional; only send what changes."""

    name: str | None = Field(default=None, min_length=1, max_length=150)
    role: Role | None = None
    is_active: bool | None = None


class ProfileUpdate(_ContactDetails):
    """A person editing their own profile. Deliberately has no role or
    is_active: nobody can change their own permissions. The email is the login
    and is not editable here either."""

    name: str | None = Field(default=None, min_length=1, max_length=150)


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class AuditLogOut(BaseModel):
    """FR1.5 — read side of the audit trail (see app/models/audit.py for
    why this table exists beyond Ch4's documented 33 entities)."""

    model_config = ConfigDict(from_attributes=True)

    audit_log_id: int
    user_id: int
    action: str
    timestamp: datetime
