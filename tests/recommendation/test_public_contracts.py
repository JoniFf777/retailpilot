import pytest
from pydantic import ValidationError

from app.schemas.recommendation import AvailabilityView, Money


def test_money_requires_positive_amount() -> None:
    for amount in ("0", "0.00", "-0.01"):
        with pytest.raises(ValidationError):
            Money(amount=amount, currency="CNY")


def test_money_keeps_decimal_string_contract() -> None:
    money = Money(amount="5999", currency="CNY")
    assert money.amount == "5999.00"
    assert isinstance(money.amount, str)


def test_availability_sale_status_is_literal() -> None:
    assert AvailabilityView(sale_status="active", available_quantity=1, in_stock=True).sale_status == "active"
    with pytest.raises(ValidationError):
        AvailabilityView(sale_status="retired", available_quantity=1, in_stock=True)
