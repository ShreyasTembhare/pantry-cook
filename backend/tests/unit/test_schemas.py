"""Tests for Pydantic schemas — validation rules, edge cases."""

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.domain.units import Unit
from app.schemas.items import ItemCreate, ItemRead, ItemUpdate, normalise_name_key


class TestNormaliseNameKey:
    def test_basic(self) -> None:
        assert normalise_name_key("Rice") == "rice"

    def test_whitespace_collapse(self) -> None:
        assert normalise_name_key("  brown   rice  ") == "brown rice"

    def test_unicode_casefold(self) -> None:
        assert normalise_name_key("Müsli") == "müsli"


class TestItemCreate:
    def test_valid(self) -> None:
        item = ItemCreate(name="Rice", quantity=Decimal("500"), unit=Unit.G)
        assert item.name == "Rice"

    def test_with_expiry(self) -> None:
        item = ItemCreate(
            name="Milk", quantity=Decimal("1"), unit=Unit.L, expires_on=date(2025, 1, 15)
        )
        assert item.expires_on == date(2025, 1, 15)

    def test_blank_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ItemCreate(name="   ", quantity=Decimal("1"), unit=Unit.G)

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ItemCreate(name="", quantity=Decimal("1"), unit=Unit.G)

    def test_negative_quantity_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ItemCreate(name="Rice", quantity=Decimal("-1"), unit=Unit.G)

    def test_quantity_too_large(self) -> None:
        with pytest.raises(ValidationError):
            ItemCreate(name="Rice", quantity=Decimal("1000001"), unit=Unit.G)

    def test_zero_quantity_allowed(self) -> None:
        item = ItemCreate(name="Rice", quantity=Decimal("0"), unit=Unit.G)
        assert item.quantity == Decimal("0")

    def test_extra_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ItemCreate(name="Rice", quantity=Decimal("1"), unit=Unit.G, bogus="x")  # type: ignore[call-arg]


class TestItemUpdate:
    def test_partial_update_name_only(self) -> None:
        update = ItemUpdate(name="Brown Rice", version=1)
        assert update.name == "Brown Rice"
        assert update.quantity is None

    def test_version_required(self) -> None:
        with pytest.raises(ValidationError):
            ItemUpdate(name="Rice")  # type: ignore[call-arg]

    def test_version_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            ItemUpdate(version=0)


class TestItemRead:
    def test_from_dict(self) -> None:
        data = {
            "id": "abc",
            "name": "Rice",
            "quantity": Decimal("500"),
            "unit": "g",
            "dimension": "mass",
            "expires_on": None,
            "version": 1,
            "created_at": "2025-01-01T00:00:00",
            "updated_at": "2025-01-01T00:00:00",
        }
        item = ItemRead(**data)
        assert item.unit == Unit.G
