"""Module 2 business logic. FR2.1-FR2.5."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.menu import MenuItem, RecipeIngredientLink
from app.schemas.menu import MenuItemCreate, MenuItemUpdate, RecipeIngredientLinkCreate


class MenuItemNotFoundError(Exception):
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


def list_menu_items(db: Session) -> list[MenuItem]:
    return list(db.scalars(select(MenuItem).order_by(MenuItem.name)))


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


def compute_profit_margin(item: MenuItem) -> None:
    """FR2.1 — profit margin = price minus recipe ingredient cost. Stubbed
    to None until Sprint 2 gives RecipeIngredientLink a real Ingredient/
    SupplierPricing to cost against; wire the real calculation in here then
    rather than changing the call site."""
    return None


def compute_is_available(item: MenuItem) -> bool:
    """FR2.4 — stock-based availability flag. Stubbed to True until Sprint
    2's Inventory Management module provides real stock levels to check
    each linked ingredient against its threshold."""
    return True
