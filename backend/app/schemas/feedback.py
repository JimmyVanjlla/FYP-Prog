from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class PortionRecommendationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    recommendation_id: int
    menu_item_id: int
    leftover_rate: Decimal
    suggested_portion_size: Decimal
    status: str
    created_at: datetime
    # The Manager's decision, for the approvals history.
    decided_by: int | None = None
    decided_at: datetime | None = None
    decision_note: str | None = None


class IdentifyHighLeftoverResult(BaseModel):
    flagged_count: int
