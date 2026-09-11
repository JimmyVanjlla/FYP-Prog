"""
Shared FastAPI dependencies: DB session access, current-user resolution,
and per-endpoint role enforcement.

FR1.3 / NFR-Security: role-based access control is enforced here, at the API
layer, on every protected endpoint — never left to the Flutter UI to hide a
button and call it secure.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.security import JWTError, decode_access_token
from app.db.session import get_db
from app.models.roles import Role
from app.models.user import User

_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

_CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    token: str = Depends(_oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
    except JWTError:
        raise _CREDENTIALS_ERROR
    if user_id is None:
        raise _CREDENTIALS_ERROR

    user = db.get(User, int(user_id))
    if user is None or not user.is_active:
        raise _CREDENTIALS_ERROR
    return user


def require_role(*allowed_roles: Role):
    """Usage: Depends(require_role(Role.RESTAURANT_MANAGER)) on any route
    that FR1.3 restricts to specific role(s)."""

    def _check(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in {r.value for r in allowed_roles}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )
        return current_user

    return _check
