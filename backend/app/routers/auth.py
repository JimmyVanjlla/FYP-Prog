from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.rate_limit import check_login_rate_limit, reset_login_rate_limit
from app.db.session import get_db
from app.schemas.user import Token, UserLogin, UserOut, UserRegister
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(data: UserRegister, db: Session = Depends(get_db)) -> UserOut:
    """FR1.1 / FR1.6. Self-registering as Restaurant Owner/Manager is only
    allowed until the first one exists (see register_user_self_service) —
    after that, an existing Manager creates further Manager/Owner accounts
    via POST /users."""
    try:
        user = auth_service.register_user_self_service(db, data)
    except auth_service.DuplicateEmailError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email address already exists.",
        )
    except auth_service.PrivilegedRoleAlreadyProvisionedError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"A {data.role.value} account already exists. Ask an existing "
                "Restaurant Manager to create this account for you instead."
            ),
        )
    return user


@router.post("/login", response_model=Token)
def login(data: UserLogin, db: Session = Depends(get_db)) -> Token:
    """FR1.2 / FR1.7 — the error message is identical whether the email
    doesn't exist or the password is wrong, by design.

    NFR-Security: rate-limited per email (app/core/rate_limit.py) — raises
    429 before even touching the DB once the attempt count for this email
    is exceeded within the configured window."""
    check_login_rate_limit(data.email)
    try:
        access_token, role = auth_service.authenticate_user(db, data.email, data.password)
    except auth_service.InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        )
    reset_login_rate_limit(data.email)
    return Token(access_token=access_token, role=role)
