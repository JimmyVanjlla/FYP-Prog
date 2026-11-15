from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core import meal_periods

MealPeriod = Literal["Breakfast", "Lunch", "Dinner"]


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
    # When the dish is served. Prep, forecasts and leftovers only consider it
    # in these periods.
    meal_periods: list[MealPeriod] = Field(default_factory=lambda: list(meal_periods.DEFAULT), min_length=1)


class MenuItemUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = None
    price: Decimal | None = Field(default=None, gt=0)
    category: str | None = Field(default=None, min_length=1, max_length=50)
    is_active: bool | None = None
    meal_periods: list[MealPeriod] | None = Field(default=None, min_length=1)


class MenuItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    menu_item_id: int
    name: str
    description: str | None
    price: Decimal
    category: str
    is_active: bool
    meal_periods: list[str] = Field(default_factory=lambda: list(meal_periods.DEFAULT))
    created_at: datetime
    recipe_links: list[RecipeIngredientLinkOut] = []

    @field_validator("meal_periods", mode="before")
    @classmethod
    def _split_stored_text(cls, value):
        # The database keeps "Lunch,Dinner"; the API speaks in lists.
        return meal_periods.from_text(value) if isinstance(value, str) else value

    # FR2.1 — profit margin per item: price minus linked ingredient cost
    # (via Module 9's SupplierPricing); None only when no recipe is
    # defined yet (see app/services/menu.py).
    profit_margin: Decimal | None = None
    # FR2.4 — stock-based availability flag: False the moment any linked
    # ingredient's on-hand stock can't cover one more serving.
    is_available: bool = True
    # FR2.4 — an ingredient in the recipe is under its low-stock threshold.
    has_low_stock_ingredient: bool = False
