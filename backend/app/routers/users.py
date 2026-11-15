from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import get_current_user, require_role
from app.models.audit import AuditLog
from app.models.roles import Role
from app.models.user import User
from app.schemas.user import AuditLogOut, PasswordChange, ProfileUpdate, UserOut, UserRegister, UserUpdate
from app.services import accounts as account_service
from app.services import auth as auth_service

router = APIRouter(prefix="/users", tags=["users"])

# Only the people who run the restaurant create, change or review accounts.
# Everyone else is given an account by one of them; nobody registers
# themselves once the first Manager or Owner exists (see
# app/services/auth.py::register_user_self_service).
_ACCOUNT_ADMINS = (Role.RESTAURANT_MANAGER, Role.RESTAURANT_OWNER)

# Accounts for the people who run the restaurant. A Manager can create and
# manage every other role, but only an Owner can create a Manager or Owner, or
# change one.
_TOP_ROLES = {Role.RESTAURANT_MANAGER.value, Role.RESTAURANT_OWNER.value}


def _role_value(role) -> str:
    return role.value if isinstance(role, Role) else str(role)


def _require_owner_for_top_roles(actor: User, *, roles: list) -> None:
    """403 if a Manager is touching a Manager or Owner role; Owners may do anything."""
    if _role_value(actor.role) == Role.RESTAURANT_OWNER.value:
        return
    if any(_role_value(r) in _TOP_ROLES for r in roles if r is not None):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only a Restaurant Owner can create or change Manager and Owner accounts.",
        )


@router.get("/me", response_model=UserOut)
def read_current_user(current_user: User = Depends(get_current_user)) -> UserOut:
    return current_user


# The /me routes come before /{user_id}, which would otherwise try to read "me"
# as a number.
@router.patch("/me", response_model=UserOut)
def update_own_profile(
    data: ProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserOut:
    """Anyone can view and edit their own profile (name and contact details).
    There is no role or is_active here: nobody changes their own permissions,
    and the email is the login."""
    for field, value in data.model_dump(exclude_unset=True).items():
        if field == "name" and value is None:
            continue  # a name cannot be cleared
        setattr(current_user, field, value)
    db.commit()
    db.refresh(current_user)
    return current_user


@router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT)
def change_own_password(
    data: PasswordChange,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    try:
        auth_service.change_password(
            db, current_user, current_password=data.current_password, new_password=data.new_password
        )
    except auth_service.WrongCurrentPasswordError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Your current password is incorrect.")


@router.get("", response_model=list[UserOut])
def list_users(
    deleted: bool = False,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role(*_ACCOUNT_ADMINS)),
) -> list[UserOut]:
    """The staff list, or with ?deleted=true the accounts deleted in the last
    60 days (newest first), which can still be restored. Accounts past that
    are purged and in neither list."""
    query = db.query(User)
    if deleted:
        account_service.purge_expired_deleted_users(db)
        query = query.filter(User.deleted_at.is_not(None)).filter(User.purged_at.is_(None))
        return list(query.order_by(User.deleted_at.desc()).limit(limit).offset(offset).all())
    return list(query.filter(User.deleted_at.is_(None)).order_by(User.name).limit(limit).offset(offset).all())


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_staff_account(
    data: UserRegister,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(*_ACCOUNT_ADMINS)),
) -> UserOut:
    """FR1.1/FR1.4 — a Manager or Owner provisioning a staff account directly.
    A Manager can create every role except Manager and Owner; an Owner can
    create any. This is the
    counterpart to POST /auth/register's self-service path, which only
    allows Owner/Manager once (see
    app/services/auth.py::register_user_self_service) — beyond that
    bootstrap window, an existing Manager has to be the one creating
    further Manager/Owner accounts."""
    _require_owner_for_top_roles(admin, roles=[data.role])
    try:
        return auth_service.register_user(db, data)
    except auth_service.DuplicateEmailError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email address already exists.",
        )


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    data: UserUpdate,
    db: Session = Depends(get_db),
    manager: User = Depends(require_role(*_ACCOUNT_ADMINS)),
) -> UserOut:
    """FR1.4 — Restaurant Manager or Owner deactivates/reassigns roles for staff
    accounts. Creation happens via POST /auth/register (self-service) or
    POST /users (Manager-provisioned); this endpoint covers deactivate +
    role reassignment for an account that already exists."""
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    # A Manager cannot touch a Manager or Owner account, nor promote anyone to one.
    _require_owner_for_top_roles(manager, roles=[target.role, data.role])

    changes = data.model_dump(exclude_unset=True)
    # name, role and is_active are required on an account: sending null for one
    # means "no change", not "blank it". The contact details may be cleared.
    changes = {k: v for k, v in changes.items() if v is not None or k not in {"name", "role", "is_active"}}
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


@router.delete("/{user_id}", response_model=UserOut)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(*_ACCOUNT_ADMINS)),
) -> UserOut:
    """Delete a deactivated account: it leaves the staff list and can be
    restored from the Deleted list for 60 days, then it is purged."""
    target = db.get(User, user_id)
    if target is None or target.purged_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    if target.user_id == admin.user_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="You cannot delete your own account.")
    _require_owner_for_top_roles(admin, roles=[target.role])
    try:
        account_service.delete_account(db, target)
    except account_service.AccountNotDeactivatedError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Deactivate the account before deleting it."
        )
    db.add(AuditLog(user_id=admin.user_id, action=f"delete_user:{user_id}"))
    db.commit()
    return target


@router.post("/{user_id}/restore", response_model=UserOut)
def restore_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(*_ACCOUNT_ADMINS)),
) -> UserOut:
    """Bring a deleted account back (deactivated; reactivate it from the staff list)."""
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    _require_owner_for_top_roles(admin, roles=[target.role])
    try:
        account_service.restore_account(db, target)
    except account_service.AccountPurgedError:
        raise HTTPException(
            status_code=status.HTTP_410_GONE, detail="This account was removed permanently after 60 days."
        )
    except account_service.AccountNotDeletedError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This account is not deleted.")
    db.add(AuditLog(user_id=admin.user_id, action=f"restore_user:{user_id}"))
    db.commit()
    return target


@router.get("/audit-logs", response_model=list[AuditLogOut])
def list_audit_logs(
    user_id: int | None = None,
    limit: int = 200,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role(*_ACCOUNT_ADMINS)),
) -> list[AuditLogOut]:
    """FR1.5 — the read side of the audit trail. Sprint 1 only ever wrote
    to AuditLog (register/login/update_user); nothing could actually view
    it until now, which undercut the "for audit trail purposes" the FR
    itself names as the point of logging in the first place."""
    stmt = select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(min(limit, 1000))
    if user_id is not None:
        stmt = stmt.where(AuditLog.user_id == user_id)
    return list(db.scalars(stmt))
