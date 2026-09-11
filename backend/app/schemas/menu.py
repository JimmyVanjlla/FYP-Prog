from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class RecipeIngredientLinkCreate(BaseModel):
    """FR2.2 / FR2.5 — quantity_per_serving must be > 0; gt=0 also rejects
    non-numeric input since Pydantic fails type coercion before the
    constraint even runs."""

    ingredient_id: int
    quantity_per_serving: Decimal = Field(gt=0)


class RecipeIngredientLinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    link_id: int
    ingredient_id: int
    quantity_per_serving: Decimal


class MenuItemCreate(BaseModel):
    """FR2.1 / FR2.5 — price must be > 0 (also rejects zero/negative/
    non-numeric per FR2.5)."""

    name: str = Field(min_length=1, max_length=150)
    description: str | None = None
    price: Decimal = Field(gt=0)
    category: str = Field(min_length=1, max_length=50)


class MenuItemUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = None
    price: Decimal | None = Field(default=None, gt=0)
    category: str | None = Field(default=None, min_length=1, max_length=50)
    is_active: bool | None = None


class MenuItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    menu_item_id: int
    name: str
    description: str | None
    price: Decimal
    category: str
    is_active: bool
    created_at: datetime
    recipe_links: list[RecipeIngredientLinkOut] = []
    # FR2.1 — profit margin per item: price minus linked ingredient cost
    # (via Module 9's SupplierPricing); None only when no recipe is
    # defined yet (see app/services/menu.py).
    profit_margin: Decimal | None = None
    # FR2.4 — stock-based availability flag: False the moment any linked
    # ingredient's on-hand stock can't cover one more serving.
    is_available: bool = True
