from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import get_current_user, require_role
from app.models.audit import AuditLog
from app.models.roles import Role
from app.models.user import User
from app.schemas.user import UserOut, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserOut)
def read_current_user(current_user: User = Depends(get_current_user)) -> UserOut:
    return current_user


@router.get("", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db),
    _manager: User = Depends(require_role(Role.RESTAURANT_MANAGER)),
) -> list[UserOut]:
    return list(db.query(User).order_by(User.name).all())


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    data: UserUpdate,
    db: Session = Depends(get_db),
    manager: User = Depends(require_role(Role.RESTAURANT_MANAGER)),
) -> UserOut:
    """FR1.4 — Restaurant Manager creates/deactivates/reassigns roles for
    staff accounts. Creation itself happens via POST /auth/register; this
    endpoint covers deactivate + role reassignment."""
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    changes = data.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(target, field, value.value if isinstance(value, Role) else value)

    if changes:
        db.add(
            AuditLog(
                user_id=manager.user_id,
                action=f"update_user:{user_id}:{','.join(changes.keys())}",
            )
        )
    db.commit()
    db.refresh(target)
    return target
