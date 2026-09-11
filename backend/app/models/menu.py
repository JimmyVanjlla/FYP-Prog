"""
Module 2: Menu & Recipe Management — MenuItem [M2], RecipeIngredientLink [M2]
(Ch4 §4.3.1). Backs FR2.1-FR2.5.

RecipeIngredientLink.ingredient_id is a real FK to Ingredient.ingredient_id
(Module 3: Inventory Management, added in Sprint 2). No ORM-level
relationship() back to Ingredient is declared here, though, to keep Module 2
from importing Module 3's model module — the FK constraint alone is enough
for referential integrity and for Module 3's services to query through it.
"""
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class MenuItem(Base):
    __tablename__ = "menu_items"

    menu_item_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    recipe_links: Mapped[list["RecipeIngredientLink"]] = relationship(
        back_populates="menu_item", cascade="all, delete-orphan"
    )


class RecipeIngredientLink(Base):
    __tablename__ = "recipe_ingredient_links"

    link_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    menu_item_id: Mapped[int] = mapped_column(
        ForeignKey("menu_items.menu_item_id"), nullable=False
    )
    ingredient_id: Mapped[int] = mapped_column(
        ForeignKey("ingredients.ingredient_id"), nullable=False
    )
    quantity_per_serving: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)

    menu_item: Mapped["MenuItem"] = relationship(back_populates="recipe_links")
