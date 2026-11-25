"""Incoming orders and what the kitchen has actually served.

Orders arrive as "pending"; Kitchen Staff move them to "preparing" and then
"completed". The portions of completed orders are the *served* figure that
leftover is worked out from (see app/services/kitchen.py::leftover_summary).

There is no till or point-of-sale connected to this system (Ch1 §1.2.2), so
for the demonstration `simulate_orders` creates a believable set of incoming
orders for a meal period.
"""
import random
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import meal_periods
from app.models.forecasting import ORDER_STATUSES, Forecast, Order
from app.models.menu import MenuItem
from app.services import kitchen as kitchen_service

_RANK = {status: i for i, status in enumerate(ORDER_STATUSES)}


class OrderNotFoundError(Exception):
    pass


class InvalidStatusChangeError(Exception):
    """An order only moves forwards: pending, then preparing, then completed."""


def _with_names(db: Session, orders: list[Order]) -> list[dict]:
    names = {
        mid: name
        for mid, name in db.execute(
            select(MenuItem.menu_item_id, MenuItem.name).where(MenuItem.menu_item_id.in_({o.menu_item_id for o in orders}))
        )
    }
    return [
        {
            "order_id": o.order_id,
            "menu_item_id": o.menu_item_id,
            "menu_item_name": names.get(o.menu_item_id),
            "quantity": o.quantity,
            "meal_period": o.meal_period,
            "order_date": o.order_date,
            "status": o.status,
            "created_at": o.created_at,
        }
        for o in orders
    ]


def list_orders(
    db: Session, *, order_date: date, meal_period: str | None = None, status: str | None = None
) -> list[dict]:
    stmt = select(Order).where(Order.order_date == order_date)
    if meal_period:
        stmt = stmt.where(Order.meal_period == meal_period)
    if status:
        stmt = stmt.where(Order.status == status)
    orders = list(db.scalars(stmt.order_by(Order.created_at, Order.order_id)))
    return _with_names(db, orders)


def set_status(db: Session, order_id: int, new_status: str) -> dict:
    order = db.get(Order, order_id)
    if order is None:
        raise OrderNotFoundError
    if new_status not in _RANK or _RANK[new_status] <= _RANK[order.status]:
        raise InvalidStatusChangeError
    order.status = new_status
    db.commit()
    db.refresh(order)
    return _with_names(db, [order])[0]


def complete_all(db: Session, *, order_date: date, meal_period: str) -> int:
    """Mark every order of the meal period that is not yet completed as completed."""
    orders = db.scalars(
        select(Order)
        .where(Order.order_date == order_date)
        .where(Order.meal_period == meal_period)
        .where(Order.status != "completed")
    ).all()
    for order in orders:
        order.status = "completed"
    db.commit()
    return len(orders)


def simulate_orders(
    db: Session, *, order_date: date, meal_period: str, rng: random.Random | None = None
) -> list[dict]:
    """Create pending orders for every dish served at the meal period that has none
    yet: roughly 60 to 100 per cent of the portions the kitchen prepared (or, if
    prep was not confirmed, of the forecast), in tickets of 1 to 3 portions.
    Dishes that already have orders are left alone, so pressing it twice does
    not double the sales."""
    rng = rng or random.Random()
    already = {
        mid
        for (mid,) in db.execute(
            select(Order.menu_item_id).where(Order.order_date == order_date).where(Order.meal_period == meal_period)
        )
    }
    tickets: list[tuple[int, int]] = []
    for item in db.scalars(select(MenuItem).where(MenuItem.is_active.is_(True))):
        if item.menu_item_id in already or not meal_periods.serves(item.meal_periods, meal_period):
            continue
        base = kitchen_service._prepared_quantity_for(
            db, menu_item_id=item.menu_item_id, meal_period=meal_period, day=order_date
        )
        if base is None:
            forecast = db.scalars(
                select(Forecast)
                .where(Forecast.menu_item_id == item.menu_item_id)
                .where(Forecast.meal_period == meal_period)
                .where(Forecast.forecast_date == order_date)
            ).first()
            base = forecast.predicted_quantity if forecast is not None else None
        if base is None or base <= 0:
            continue
        remaining = max(1, round(float(base) * rng.uniform(0.6, 1.0)))
        while remaining > 0:
            quantity = min(remaining, rng.choice([1, 1, 2, 2, 3]))
            tickets.append((item.menu_item_id, quantity))
            remaining -= quantity

    rng.shuffle(tickets)
    now = datetime.now(timezone.utc)
    created = [
        Order(
            menu_item_id=mid,
            quantity=quantity,
            meal_period=meal_period,
            order_date=order_date,
            status="pending",
            created_at=now - timedelta(seconds=(len(tickets) - i) * 30),
        )
        for i, (mid, quantity) in enumerate(tickets)
    ]
    db.add_all(created)
    db.commit()
    for order in created:
        db.refresh(order)
    return _with_names(db, created) if created else []
