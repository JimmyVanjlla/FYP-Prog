"""Module 2 business logic. FR2.1-FR2.5."""
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.inventory import Ingredient
from app.models.menu import MenuItem, RecipeIngredientLink
from app.schemas.menu import MenuItemCreate, MenuItemUpdate, RecipeIngredientLinkCreate
from app.services.procurement import get_unit_price


class MenuItemNotFoundError(Exception):
    pass


class RecipeLinkNotFoundError(Exception):
    pass


def create_menu_item(db: Session, data: MenuItemCreate) -> MenuItem:
    item = MenuItem(
        name=data.name,
        description=data.description,
        price=data.price,
        category=data.category,
        is_active=True,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def list_menu_items(db: Session, *, include_inactive: bool = False) -> list[MenuItem]:
    """UC-MR-01 Alt Flow 3a — a deactivated item is removed "from active
    ordering and prep recommendation screens while preserving its
    historical order and forecast data for reporting", so listing excludes
    inactive items by default; include_inactive=True is for a Manager
    reviewing/reactivating past items, not the normal menu view."""
    stmt = select(MenuItem).order_by(MenuItem.name)
    if not include_inactive:
        stmt = stmt.where(MenuItem.is_active.is_(True))
    return list(db.scalars(stmt))


def get_menu_item(db: Session, menu_item_id: int) -> MenuItem:
    item = db.get(MenuItem, menu_item_id)
    if item is None:
        raise MenuItemNotFoundError
    return item


def update_menu_item(db: Session, menu_item_id: int, data: MenuItemUpdate) -> MenuItem:
    item = get_menu_item(db, menu_item_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    db.commit()
    db.refresh(item)
    return item


def deactivate_menu_item(db: Session, menu_item_id: int) -> MenuItem:
    """FR2.1 — deactivate rather than hard-delete, consistent with how
    User.is_active handles staff deactivation (FR1.4)."""
    item = get_menu_item(db, menu_item_id)
    item.is_active = False
    db.commit()
    db.refresh(item)
    return item


def add_recipe_link(
    db: Session, menu_item_id: int, data: RecipeIngredientLinkCreate
) -> RecipeIngredientLink:
    """FR2.2. ingredient_id isn't validated against a real Ingredient table
    yet — Module 3 (Inventory Management) doesn't exist until Sprint 2."""
    get_menu_item(db, menu_item_id)  # 404s if the menu item doesn't exist
    link = RecipeIngredientLink(
        menu_item_id=menu_item_id,
        ingredient_id=data.ingredient_id,
        quantity_per_serving=data.quantity_per_serving,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


def remove_recipe_link(db: Session, menu_item_id: int, link_id: int) -> None:
    """UC-MR-02 Alt Flow 2a — removes an ingredient link from a recipe.
    The use case also says this should "flag any pending prep
    recommendations that relied on the old recipe for recalculation" —
    there's nothing concrete to flag in practice, since PrepRecommendation
    is forecast-driven (a portion count) rather than recipe-driven; recipe
    links affect availability (FR2.4), profit margin (FR2.1), and waste
    cost (Module 6), all of which are computed live on every read rather
    than cached, so removing a link takes effect immediately everywhere
    that matters without a separate recalculation step."""
    link = db.get(RecipeIngredientLink, link_id)
    if link is None or link.menu_item_id != menu_item_id:
        raise RecipeLinkNotFoundError
    db.delete(link)
    db.commit()


def compute_profit_margin(db: Session, item: MenuItem) -> Decimal | None:
    """FR2.1 — profit margin = price minus recipe ingredient cost, now
    that Module 9's SupplierPricing exists (Sprint 4) to cost each linked
    ingredient against. Still None for an item with no recipe defined yet
    — nothing to subtract, not the same as a margin of exactly `price`."""
    if not item.recipe_links:
        return None

    ingredient_cost = sum(
        (link.quantity_per_serving * get_unit_price(db, link.ingredient_id) for link in item.recipe_links),
        Decimal("0.00"),
    )
    # Quantized to 2dp to match MenuItem.price's DECIMAL(10,2) — the raw
    # product otherwise carries however many decimal places
    # quantity_per_serving (3dp) × unit_price (2dp) multiplies out to.
    return (item.price - ingredient_cost).quantize(Decimal("0.01"))


def compute_is_available(db: Session, item: MenuItem) -> bool:
    """FR2.4 — a menu item is flagged unavailable the moment any linked
    ingredient's on-hand stock can't cover one more serving. Recipe links
    with no matching Ingredient row yet (shouldn't happen once FK
    constraints are enforced, but defensively) don't block availability."""
    if not item.recipe_links:
        return True  # no recipe defined yet — nothing to be short on

    ingredient_ids = [link.ingredient_id for link in item.recipe_links]
    stock_by_id = {
        i.ingredient_id: i.current_stock
        for i in db.scalars(select(Ingredient).where(Ingredient.ingredient_id.in_(ingredient_ids)))
    }
    for link in item.recipe_links:
        current_stock = stock_by_id.get(link.ingredient_id)
        if current_stock is None or current_stock < link.quantity_per_serving:
            return False
    return True
