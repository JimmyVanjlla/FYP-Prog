"""
Imports every SQLAlchemy model so Base.metadata is fully populated before
Alembic autogenerates a migration or a test spins up an in-memory schema.

Add the import here whenever a new model module is added in a later sprint —
nothing else needs to change for Alembic to pick it up.
"""
from app.db.base import Base  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.menu import MenuItem, RecipeIngredientLink  # noqa: F401
from app.models.audit import AuditLog  # noqa: F401
from app.models.config import SystemConfig  # noqa: F401
from app.models.inventory import (  # noqa: F401
    Ingredient,
    StockBatch,
    StockAdjustment,
    RestockingRequest,
)
from app.models.forecasting import Order, Forecast, ForecastAccuracy  # noqa: F401
from app.models.kitchen import (  # noqa: F401
    PrepRecommendation,
    PrepConfirmation,
    LeftoverLog,
    Notification,
)
from app.models.waste import WasteLog, WasteReductionTrend  # noqa: F401
from app.models.feedback import PortionRecommendation  # noqa: F401
from app.models.staffing import (  # noqa: F401
    ShiftSchedule,
    StaffingRecommendation,
    ShiftAssignment,
    ShiftClosingReport,
)
from app.models.procurement import (  # noqa: F401
    Supplier,
    SupplierPricing,
    ProcurementRecommendation,
    PurchaseOrder,
    PurchaseOrderItem,
    Budget,
    SupplierDiscrepancy,
)
from app.models.delivery import Delivery, DeliveryItem, DeliveryDiscrepancy  # noqa: F401
from app.models.report import Report  # noqa: F401
