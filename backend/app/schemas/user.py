from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.roles import Role


class UserRegister(BaseModel):
    """FR1.1 — name, email, and password are the only inputs required."""

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
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: Role


class UserUpdate(BaseModel):
    """FR1.4 — Restaurant Manager updates a staff account: reassign role
    and/or activate/deactivate. All fields optional; only send what changes."""

    role: Role | None = None
    is_active: bool | None = None
