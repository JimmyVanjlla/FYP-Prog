from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.dates import restaurant_today
from app.db.session import get_db
from app.deps import get_current_user, require_role
from app.models.roles import Role
from app.models.user import User
from app.services import orders as order_service

router = APIRouter(prefix="/orders", tags=["orders"])

MealPeriod = Literal["Breakfast", "Lunch", "Dinner"]


class KitchenOrderOut(BaseModel):
    order_id: int
    menu_item_id: int
    menu_item_name: str | None = None
    quantity: int
    meal_period: str
    order_date: date
    status: str
    created_at: datetime | None = None


class OrderStatusUpdate(BaseModel):
    status: Literal["preparing", "completed"]


class MealPeriodRequest(BaseModel):
    meal_period: MealPeriod
    order_date: date | None = None


class CountOut(BaseModel):
    count: int


@router.get("", response_model=list[KitchenOrderOut])
def list_orders(
    order_date: date | None = None,
    meal_period: MealPeriod | None = None,
    status_filter: Literal["pending", "preparing", "completed"] | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[KitchenOrderOut]:
    """The day's orders (today unless a date is given), oldest first."""
    return order_service.list_orders(
        db, order_date=order_date or restaurant_today(), meal_period=meal_period, status=status_filter
    )


@router.patch("/{order_id}/status", response_model=KitchenOrderOut)
def update_order_status(
    order_id: int,
    data: OrderStatusUpdate,
    db: Session = Depends(get_db),
    _staff: User = Depends(require_role(Role.KITCHEN_STAFF, Role.RESTAURANT_MANAGER)),
) -> KitchenOrderOut:
    """Kitchen Staff mark an incoming order as being prepared, then completed."""
    try:
        return order_service.set_status(db, order_id, data.status)
    except order_service.OrderNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found.")
    except order_service.InvalidStatusChangeError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An order moves from pending to preparing to completed, never backwards.",
        )


@router.post("/complete-all", response_model=CountOut)
def complete_all(
    data: MealPeriodRequest,
    db: Session = Depends(get_db),
    _staff: User = Depends(require_role(Role.KITCHEN_STAFF, Role.RESTAURANT_MANAGER)),
) -> CountOut:
    """Mark everything still open for the meal period as completed."""
    count = order_service.complete_all(
        db, order_date=data.order_date or restaurant_today(), meal_period=data.meal_period
    )
    return CountOut(count=count)


@router.post("/simulate", response_model=list[KitchenOrderOut], status_code=status.HTTP_201_CREATED)
def simulate_orders(
    data: MealPeriodRequest,
    db: Session = Depends(get_db),
    _staff: User = Depends(require_role(Role.KITCHEN_STAFF, Role.RESTAURANT_MANAGER)),
) -> list[KitchenOrderOut]:
    """Demonstration data: there is no till connected, so this creates a set of
    incoming orders for the meal period (see app/services/orders.py)."""
    return order_service.simulate_orders(
        db, order_date=data.order_date or restaurant_today(), meal_period=data.meal_period
    )
