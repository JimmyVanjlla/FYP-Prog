from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import get_current_user, require_role
from app.models.roles import Role
from app.models.user import User
from app.schemas.config import SystemConfigOut, SystemConfigUpdate
from app.services import config as config_service

router = APIRouter(prefix="/config", tags=["config"])


@router.get("", response_model=SystemConfigOut)
def read_config(
    db: Session = Depends(get_db), _user: User = Depends(get_current_user)
) -> SystemConfigOut:
    """Readable by any authenticated role — every module's UI needs to
    know the active thresholds (e.g. what counts as "low stock" right
    now), not just the Manager who can change them."""
    return config_service.get_or_create_config(db)


@router.patch("", response_model=SystemConfigOut)
def update_config(
    data: SystemConfigUpdate,
    db: Session = Depends(get_db),
    _manager: User = Depends(require_role(Role.RESTAURANT_MANAGER)),
) -> SystemConfigOut:
    """FR3.3 / FR7.5 — Ch3 §3.4.2's Restaurant Manager use-case list:
    "configure system settings"."""
    return config_service.update_config(db, data)
