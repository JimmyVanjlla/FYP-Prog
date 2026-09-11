from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class SupplierCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    contact_info: str = Field(min_length=1, max_length=255)


class SupplierOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    supplier_id: int
    name: str
    contact_info: str
    is_active: bool


class SupplierPricingCreate(BaseModel):
    supplier_id: int
    ingredient_id: int
    unit_price: Decimal = Field(gt=0)


class SupplierPricingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    pricing_id: int
    supplier_id: int
    ingredient_id: int
    unit_price: Decimal


class ProcurementRecommendationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    recommendation_id: int
    ingredient_id: int
    forecast_id: int | None
    recommended_quantity: Decimal


class PurchaseOrderLineItem(BaseModel):
    ingredient_id: int
    quantity: Decimal = Field(gt=0)  # FR9.6


class PurchaseOrderCreate(BaseModel):
    supplier_id: int
    line_items: list[PurchaseOrderLineItem] = Field(min_length=1)


class PurchaseOrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    item_id: int
    ingredient_id: int
    quantity: Decimal
    unit_price: Decimal


class PurchaseOrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    po_id: int
    supplier_id: int
    created_by: int
    approved_by: int | None
    status: str
    total_cost: Decimal
    created_at: datetime
    # FR9.6 — warning, not a block, when the order would exceed the
    # remaining monthly budget.
    exceeds_budget: bool = False


class BudgetSet(BaseModel):
    month: date
    budget_limit: Decimal = Field(gt=0)


class BudgetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    budget_id: int
    month: date
    budget_limit: Decimal
    set_by: int


class SupplierDiscrepancyCreate(BaseModel):
    po_id: int
    supplier_id: int
    description: str = Field(min_length=1)


class SupplierDiscrepancyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    discrepancy_id: int
    po_id: int
    supplier_id: int
    description: str
    status: str


class BudgetUtilisationOut(BaseModel):
    """UC-PS-06 "View Monthly Budget Utilisation"."""

    month: date
    budget_limit: Decimal
    spent: Decimal
    remaining: Decimal
    utilisation_pct: Decimal
