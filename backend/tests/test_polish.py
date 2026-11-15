"""Small fixes from reviewing every role: reasons must be words, portions whole."""
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.kitchen import PrepConfirmationCreate
from app.schemas.procurement import RejectionReason, SupplierDiscrepancyCreate
from app.services.kitchen import _whole_portions


@pytest.mark.parametrize("bad", ["123123123", "??? !!", "12 34 56"])
def test_rejection_reason_needs_a_letter(bad):
    with pytest.raises(ValidationError):
        RejectionReason(reason=bad)


def test_rejection_reason_with_words_is_accepted_and_trimmed():
    assert RejectionReason(reason="  Over budget 2  ").reason == "Over budget 2"


def test_supplier_issue_description_needs_a_letter():
    with pytest.raises(ValidationError):
        SupplierDiscrepancyCreate(po_id=1, supplier_id=1, description="4444")
    ok = SupplierDiscrepancyCreate(po_id=1, supplier_id=1, description="Late and short by 2 kg")
    assert ok.description.startswith("Late")


def test_prep_deviation_reason_needs_a_letter_when_given():
    with pytest.raises(ValidationError):
        PrepConfirmationCreate(confirmed_quantity=Decimal("30"), deviation_reason="123")
    # Nothing given is still allowed here; the service decides if one is required.
    assert PrepConfirmationCreate(confirmed_quantity=Decimal("30")).deviation_reason is None
    assert PrepConfirmationCreate(confirmed_quantity=Decimal("30"), deviation_reason="Big booking").deviation_reason


@pytest.mark.parametrize(
    "raw, expected",
    [("24.77", "25"), ("24.40", "24"), ("12.50", "13"), (7, "7"), (Decimal("0.49"), "0")],
)
def test_portions_are_rounded_to_the_nearest_whole_dish(raw, expected):
    assert _whole_portions(raw) == Decimal(expected)
