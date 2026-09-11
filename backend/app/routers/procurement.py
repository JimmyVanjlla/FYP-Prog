from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import get_current_user, require_role
from app.models.roles import Role
from app.models.user import User
from app.schemas.procurement import (
    BudgetOut,
    BudgetSet,
    BudgetUtilisationOut,
    ProcurementRecommendationOut,
    PurchaseOrderCreate,
    PurchaseOrderOut,
    SupplierCreate,
    SupplierDiscrepancyCreate,
    SupplierDiscrepancyOut,
    SupplierOut,
    SupplierPricingCreate,
    SupplierPricingOut,
)
from app.services import procurement as procurement_service

router = APIRouter(prefix="/procurement", tags=["procurement"])

_PROCUREMENT_ROLES = (Role.PROCUREMENT_OFFICER, Role.RESTAURANT_MANAGER)


@router.get("/suppliers", response_model=list[SupplierOut])
def list_suppliers(db: Session = Depends(get_db), _user: User = Depends(get_current_user)) -> list[SupplierOut]:
    """FR9.1."""
    return procurement_service.list_suppliers(db)


@router.post("/suppliers", response_model=SupplierOut, status_code=status.HTTP_201_CREATED)
def create_supplier(
    data: SupplierCreate, db: Session = Depends(get_db), _staff: User = Depends(require_role(*_PROCUREMENT_ROLES))
) -> SupplierOut:
    """FR9.1."""
    return procurement_service.create_supplier(db, name=data.name, contact_info=data.contact_info)


@router.patch("/suppliers/{supplier_id}/deactivate", response_model=SupplierOut)
def deactivate_supplier(
    supplier_id: int,
    db: Session = Depends(get_db),
    _staff: User = Depends(require_role(*_PROCUREMENT_ROLES)),
) -> SupplierOut:
    """UC-PS-04 Alt Flow 3a."""
    try:
        return procurement_service.deactivate_supplier(db, supplier_id)
    except procurement_service.NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found.")


@router.post("/suppliers/pricing", response_model=SupplierPricingOut, status_code=status.HTTP_201_CREATED)
def set_supplier_pricing(
    data: SupplierPricingCreate,
    db: Session = Depends(get_db),
    _staff: User = Depends(require_role(*_PROCUREMENT_ROLES)),
) -> SupplierPricingOut:
    """FR9.1."""
    return procurement_service.set_supplier_pricing(
        db, supplier_id=data.supplier_id, ingredient_id=data.ingredient_id, unit_price=data.unit_price
    )


@router.get("/suppliers/pricing", response_model=list[SupplierPricingOut])
def list_supplier_pricing(
    supplier_id: int | None = None,
    ingredient_id: int | None = None,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[SupplierPricingOut]:
    """FR9.1 — the read side of set_supplier_pricing; a "supplier
    directory with pricing" needs to be viewable, not just set once."""
    return procurement_service.list_supplier_pricing(db, supplier_id=supplier_id, ingredient_id=ingredient_id)


@router.get("/recommendations", response_model=list[ProcurementRecommendationOut])
def list_recommendations(
    db: Session = Depends(get_db), _staff: User = Depends(require_role(*_PROCUREMENT_ROLES))
) -> list[ProcurementRecommendationOut]:
    """FR9.2."""
    return procurement_service.list_procurement_recommendations(db)


@router.post("/recommendations/generate", response_model=list[ProcurementRecommendationOut])
def generate_recommendations(
    db: Session = Depends(get_db), _staff: User = Depends(require_role(*_PROCUREMENT_ROLES))
) -> list[ProcurementRecommendationOut]:
    """FR9.2."""
    return procurement_service.generate_procurement_recommendations(db)


@router.get("/purchase-orders", response_model=list[PurchaseOrderOut])
def list_purchase_orders(
    status_filter: str | None = None,
    db: Session = Depends(get_db),
    _staff: User = Depends(require_role(*_PROCUREMENT_ROLES)),
) -> list[PurchaseOrderOut]:
    return procurement_service.list_purchase_orders(db, status=status_filter)


@router.post("/purchase-orders", response_model=PurchaseOrderOut, status_code=status.HTTP_201_CREATED)
def create_purchase_order(
    data: PurchaseOrderCreate,
    db: Session = Depends(get_db),
    officer: User = Depends(require_role(Role.PROCUREMENT_OFFICER)),
) -> PurchaseOrderOut:
    """FR9.3 / FR9.6."""
    try:
        po, exceeds_budget = procurement_service.create_purchase_order(
            db,
            supplier_id=data.supplier_id,
            created_by=officer.user_id,
            line_items=[item.model_dump() for item in data.line_items],
        )
    except procurement_service.InvalidPurchaseOrderError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Purchase orders need at least one line item with a positive quantity.",
        )
    out = PurchaseOrderOut.model_validate(po)
    out.exceeds_budget = exceeds_budget
    return out


@router.post("/purchase-orders/{po_id}/approve", response_model=PurchaseOrderOut)
def approve_purchase_order(
    po_id: int, db: Session = Depends(get_db), manager: User = Depends(require_role(Role.RESTAURANT_MANAGER))
) -> PurchaseOrderOut:
    """FR9.3."""
    try:
        return procurement_service.approve_purchase_order(db, po_id, manager.user_id)
    except procurement_service.NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase order not found.")


@router.post("/purchase-orders/{po_id}/reject", response_model=PurchaseOrderOut)
def reject_purchase_order(
    po_id: int, db: Session = Depends(get_db), _manager: User = Depends(require_role(Role.RESTAURANT_MANAGER))
) -> PurchaseOrderOut:
    """FR9.3."""
    try:
        return procurement_service.reject_purchase_order(db, po_id)
    except procurement_service.NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase order not found.")


@router.post("/budget", response_model=BudgetOut, status_code=status.HTTP_201_CREATED)
def set_budget(
    data: BudgetSet, db: Session = Depends(get_db), manager: User = Depends(require_role(Role.RESTAURANT_MANAGER))
) -> BudgetOut:
    """FR9.4."""
    return procurement_service.set_monthly_budget(
        db, month=data.month, budget_limit=data.budget_limit, set_by=manager.user_id
    )


@router.get("/budget", response_model=list[BudgetOut])
def list_budgets(
    db: Session = Depends(get_db), _staff: User = Depends(require_role(*_PROCUREMENT_ROLES))
) -> list[BudgetOut]:
    """FR9.4 — "track monthly procurement budget configuration" needs a
    way to see what's been configured, not just set it once."""
    return procurement_service.list_budgets(db)


@router.get("/budget/utilisation", response_model=BudgetUtilisationOut)
def get_budget_utilisation(
    month: date | None = None,
    db: Session = Depends(get_db),
    _staff: User = Depends(require_role(*_PROCUREMENT_ROLES)),
) -> BudgetUtilisationOut:
    """UC-PS-06 "View Monthly Budget Utilisation" — remaining budget and
    % used; previously only the raw Budget list and a boolean flag on new
    PO creation existed, no dedicated view."""
    return procurement_service.get_budget_utilisation(db, month=month)


@router.post(
    "/discrepancies", response_model=SupplierDiscrepancyOut, status_code=status.HTTP_201_CREATED
)
def flag_discrepancy(
    data: SupplierDiscrepancyCreate,
    db: Session = Depends(get_db),
    _staff: User = Depends(require_role(*_PROCUREMENT_ROLES)),
) -> SupplierDiscrepancyOut:
    """FR9.5."""
    return procurement_service.flag_supplier_discrepancy(
        db, po_id=data.po_id, supplier_id=data.supplier_id, description=data.description
    )


@router.get("/discrepancies", response_model=list[SupplierDiscrepancyOut])
def list_discrepancies(
    db: Session = Depends(get_db), _staff: User = Depends(require_role(*_PROCUREMENT_ROLES))
) -> list[SupplierDiscrepancyOut]:
    return procurement_service.list_supplier_discrepancies(db)


@router.post("/discrepancies/{discrepancy_id}/resolve", response_model=SupplierDiscrepancyOut)
def resolve_discrepancy(
    discrepancy_id: int,
    db: Session = Depends(get_db),
    _staff: User = Depends(require_role(*_PROCUREMENT_ROLES)),
) -> SupplierDiscrepancyOut:
    """UC-PS-07 Alt Flow 3a."""
    try:
        return procurement_service.resolve_supplier_discrepancy(db, discrepancy_id)
    except procurement_service.NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Discrepancy not found.")
