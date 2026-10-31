from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import get_current_user
from app.models.user import User
from app.services import notifications as notification_service

router = APIRouter(prefix="/notifications", tags=["notifications"])


class DeviceRegistration(BaseModel):
    token: str = Field(min_length=1, max_length=512)
    platform: str = Field(default="android", max_length=20)


class DeviceOut(BaseModel):
    device_token_id: int
    platform: str


@router.post("/devices", response_model=DeviceOut, status_code=status.HTTP_201_CREATED)
def register_device(
    data: DeviceRegistration,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DeviceOut:
    """FR5.4 — the app registers its FCM token after login so the backend
    knows where to push this user's notifications."""
    device = notification_service.register_device(
        db, user_id=user.user_id, token=data.token, platform=data.platform
    )
    return DeviceOut(device_token_id=device.device_token_id, platform=device.platform)


@router.post("/devices/unregister", status_code=status.HTTP_204_NO_CONTENT)
def unregister_device(
    data: DeviceRegistration,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """Called on logout."""
    notification_service.unregister_device(db, user_id=user.user_id, token=data.token)
