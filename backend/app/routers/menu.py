from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import get_current_user, require_role
from app.models.roles import Role
from app.models.user import User
from app.schemas.menu import (
    MenuItemCreate,
    MenuItemOut,
    MenuItemUpdate,
    RecipeIngredientLinkCreate,
    RecipeIngredientLinkOut,
)
from app.services import menu as menu_service

router = APIRouter(prefix="/menu-items", tags=["menu"])


def _to_out(item, db: Session) -> MenuItemOut:
    out = MenuItemOut.model_validate(item)
    out.profit_margin = menu_service.compute_profit_margin(db, item)
    out.is_available = menu_service.compute_is_available(db, item)
    return out


@router.get("", response_model=list[MenuItemOut])
def list_menu_items(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[MenuItemOut]:
    """FR2.4 — every authenticated role can view the menu list with its
    stock-based availability flag; only Managers can mutate it.
    include_inactive is for a Manager reviewing past items (UC-MR-01 Alt
    Flow 3a) — everyone else effectively only ever sees active ones since
    the default excludes deactivated items from ordering/prep screens."""
    return [_to_out(item, db) for item in menu_service.list_menu_items(db, include_inactive=include_inactive)]


@router.post("", response_model=MenuItemOut, status_code=status.HTTP_201_CREATED)
def create_menu_item(
    data: MenuItemCreate,
    db: Session = Depends(get_db),
    _manager: User = Depends(require_role(Role.RESTAURANT_MANAGER)),
) -> MenuItemOut:
    """FR2.1 / FR2.5."""
    item = menu_service.create_menu_item(db, data)
    return _to_out(item, db)


@router.put("/{menu_item_id}", response_model=MenuItemOut)
def update_menu_item(
    menu_item_id: int,
    data: MenuItemUpdate,
    db: Session = Depends(get_db),
    _manager: User = Depends(require_role(Role.RESTAURANT_MANAGER)),
) -> MenuItemOut:
    try:
        item = menu_service.update_menu_item(db, menu_item_id, data)
    except menu_service.MenuItemNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Menu item not found.")
    return _to_out(item, db)


@router.delete("/{menu_item_id}", response_model=MenuItemOut)
def deactivate_menu_item(
    menu_item_id: int,
    db: Session = Depends(get_db),
    _manager: User = Depends(require_role(Role.RESTAURANT_MANAGER)),
) -> MenuItemOut:
    """FR2.1 — deactivates rather than hard-deletes."""
    try:
        item = menu_service.deactivate_menu_item(db, menu_item_id)
    except menu_service.MenuItemNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Menu item not found.")
    return _to_out(item, db)


@router.post(
    "/{menu_item_id}/recipe-links",
    response_model=RecipeIngredientLinkOut,
    status_code=status.HTTP_201_CREATED,
)
def add_recipe_link(
    menu_item_id: int,
    data: RecipeIngredientLinkCreate,
    db: Session = Depends(get_db),
    _manager: User = Depends(require_role(Role.RESTAURANT_MANAGER)),
) -> RecipeIngredientLinkOut:
    """FR2.2 / FR2.5."""
    try:
        link = menu_service.add_recipe_link(db, menu_item_id, data)
    except menu_service.MenuItemNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Menu item not found.")
    return link


@router.delete("/{menu_item_id}/recipe-links/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_recipe_link(
    menu_item_id: int,
    link_id: int,
    db: Session = Depends(get_db),
    _manager: User = Depends(require_role(Role.RESTAURANT_MANAGER)),
) -> None:
    """UC-MR-02 Alt Flow 2a."""
    try:
        menu_service.remove_recipe_link(db, menu_item_id, link_id)
    except menu_service.RecipeLinkNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipe link not found.")
