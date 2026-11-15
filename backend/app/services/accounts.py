"""Deleting and restoring staff accounts.

Deleting an account hides it from the staff list and keeps it in a "Deleted"
list for 60 days, during which it can be restored. After that it is purged:
the person's details are wiped and the account can no longer be restored. The
row itself stays, anonymised, because audit logs, approvals and other records
still point at it.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User

RETENTION_DAYS = 60


class AccountNotDeactivatedError(Exception):
    """Only a deactivated account can be deleted."""


class AccountNotDeletedError(Exception):
    pass


class AccountPurgedError(Exception):
    """The retention period is over; the account cannot come back."""


def purge_expired_deleted_users(db: Session, *, now: datetime | None = None) -> int:
    """Anonymise accounts deleted more than 60 days ago. Called whenever the
    Deleted list is read, so no scheduled job (and no worker) is needed."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=RETENTION_DAYS)
    expired = db.scalars(select(User).where(User.deleted_at.is_not(None)).where(User.purged_at.is_(None))).all()
    purged = 0
    for user in expired:
        deleted_at = user.deleted_at if user.deleted_at.tzinfo else user.deleted_at.replace(tzinfo=timezone.utc)
        if deleted_at > cutoff:
            continue
        user.name = "Former staff member"
        user.email = f"removed-{user.user_id}@example.com"
        user.password_hash = "!"
        user.phone_number = user.address = user.emergency_contact_name = user.emergency_contact_phone = None
        user.is_active = False
        user.purged_at = now
        purged += 1
    if purged:
        db.commit()
    return purged


def delete_account(db: Session, target: User) -> User:
    if target.is_active:
        raise AccountNotDeactivatedError
    if target.deleted_at is None:
        target.deleted_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(target)
    return target


def restore_account(db: Session, target: User) -> User:
    if target.purged_at is not None:
        raise AccountPurgedError
    if target.deleted_at is None:
        raise AccountNotDeletedError
    target.deleted_at = None  # comes back deactivated; reactivate it from the staff list
    db.commit()
    db.refresh(target)
    return target
