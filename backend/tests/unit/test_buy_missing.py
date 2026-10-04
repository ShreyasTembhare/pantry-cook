"""Buying a missing line creates or increments a pantry item and clears the line."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.db.models import Item, Meal, MealLine
from app.db.repositories import ItemRepository
from app.domain.buy import buy_missing_line, parse_quantity_note
from app.domain.errors import (
    MealLineNotFoundError,
    MealNotFoundError,
    MissingNameError,
    NonIntegerCountError,
    QuantityLimitError,
    QuantityRequiredError,
    QuantityTooSmallError,
    UnitDimensionMismatchError,
)
from app.domain.units import Unit
from app.schemas.items import ItemCreate


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _item(db: Session, name: str, quantity: str, unit: Unit) -> Item:
    item = ItemRepository(db).create(ItemCreate(name=name, quantity=Decimal(quantity), unit=unit))
    db.commit()
    return item


def _meal(db: Session, lines: list[MealLine]) -> Meal:
    now = _now()
    meal = Meal(
        sentence="something warm",
        title="Weeknight soup",
        servings=2,
        steps=["Simmer."],
        status="cooked",
        cooked_at=now,
        created_at=now,
    )
    db.add(meal)
    db.flush()
    for position, line in enumerate(lines):
        line.meal_id = meal.id
        line.position = position
        db.add(line)
    db.commit()
    db.refresh(meal)
    return meal


def _missing(name: str, note: str | None = None, **extra: object) -> MealLine:
    return MealLine(
        kind="missing",
        item_name_snapshot=name,
        missing_name=name,
        missing_note=note,
        **extra,
    )


class TestParseQuantityNote:
    @pytest.mark.parametrize(
        ("note", "amount", "unit"),
        [
            ("200 g", "200", Unit.G),
            ("about 200 g", "200", Unit.G),
            ("1.5kg", "1.5", Unit.KG),
            ("1,5 kg", "1.5", Unit.KG),
            ("500 ml", "500", Unit.ML),
            ("1 L", "1", Unit.L),
            ("2 count", "2", Unit.COUNT),
        ],
    )
    def test_reads_one_measure(self, note: str, amount: str, unit: Unit) -> None:
        parsed = parse_quantity_note(note)
        assert parsed is not None
        assert parsed[0] == Decimal(amount)
        assert parsed[1] == unit

    @pytest.mark.parametrize("note", [None, "", "a splash", "200 g or 1 kg", "6 eggs", "0 g"])
    def test_notes_without_one_measure(self, note: str | None) -> None:
        assert parse_quantity_note(note) is None


class TestBuyMissingLine:
    def test_creates_from_the_note_and_clears_only_that_line(self, db_session: Session) -> None:
        meal = _meal(
            db_session,
            [
                _missing("butter", "about 200 g"),
                _missing("olive oil", "a splash"),
            ],
        )
        butter = next(line for line in meal.lines if line.missing_name == "butter")
        oil = next(line for line in meal.lines if line.missing_name == "olive oil")

        bought = buy_missing_line(db_session, meal.id, butter.id)
        db_session.commit()

        assert bought.created is True
        assert bought.item.name == "Butter"
        assert bought.quantity.unit == Unit.G
        assert Decimal(str(bought.item.quantity_base)) == Decimal("200")
        db_session.refresh(meal)
        names = [line.missing_name for line in meal.lines]
        assert names == ["olive oil"]
        assert oil.id in {line.id for line in meal.lines}

    def test_increments_the_same_name_across_units(self, db_session: Session) -> None:
        flour = _item(db_session, "Flour", "500", Unit.G)
        milk = _item(db_session, "Milk", "1", Unit.L)
        meal = _meal(
            db_session,
            [
                _missing("flour", None),
                _missing("MILK", "500 ml"),
            ],
        )
        flour_line = next(line for line in meal.lines if line.missing_name == "flour")
        milk_line = next(line for line in meal.lines if line.missing_name == "MILK")

        bought_flour = buy_missing_line(
            db_session,
            meal.id,
            flour_line.id,
            quantity=Decimal("0.2"),
            unit=Unit.KG,
        )
        bought_milk = buy_missing_line(db_session, meal.id, milk_line.id)
        db_session.commit()

        db_session.refresh(flour)
        db_session.refresh(milk)
        assert bought_flour.created is False
        assert bought_flour.item.id == flour.id
        assert Decimal(str(flour.quantity_base)) == Decimal("700")
        assert flour.display_unit == "g"
        assert flour.version == 2
        assert bought_milk.created is False
        assert bought_milk.item.id == milk.id
        assert Decimal(str(milk.quantity_base)) == Decimal("1500")
        assert milk.display_unit == "L"
        assert milk.version == 2

    def test_uses_a_stored_measure_when_the_note_has_none(self, db_session: Session) -> None:
        meal = _meal(
            db_session,
            [
                _missing(
                    "eggs",
                    None,
                    quantity_base=6,
                    dimension="count",
                    display_unit="count",
                )
            ],
        )
        line = meal.lines[0]
        bought = buy_missing_line(db_session, meal.id, line.id)
        db_session.commit()
        assert bought.created is True
        assert bought.quantity.unit == Unit.COUNT
        assert Decimal(str(bought.item.quantity_base)) == Decimal("6")

    def test_explicit_quantity_when_the_line_has_none(self, db_session: Session) -> None:
        meal = _meal(db_session, [_missing("olive oil", "a splash")])
        line = meal.lines[0]
        bought = buy_missing_line(
            db_session,
            meal.id,
            line.id,
            quantity=Decimal("250"),
            unit=Unit.ML,
        )
        db_session.commit()
        assert bought.created is True
        assert bought.item.display_unit == "ml"
        assert Decimal(str(bought.item.quantity_base)) == Decimal("250")
        db_session.refresh(meal)
        assert meal.lines == []

    def test_asks_when_the_line_has_no_quantity(self, db_session: Session) -> None:
        meal = _meal(db_session, [_missing("olive oil", "a splash")])
        line_id = meal.lines[0].id
        with pytest.raises(QuantityRequiredError):
            buy_missing_line(db_session, meal.id, line_id)
        db_session.rollback()
        db_session.refresh(meal)
        assert [line.id for line in meal.lines] == [line_id]
        assert ItemRepository(db_session).find_by_name_key("olive oil") is None

    def test_rejects_a_different_dimension_and_keeps_the_line(self, db_session: Session) -> None:
        oil = _item(db_session, "olive oil", "1", Unit.COUNT)
        meal = _meal(db_session, [_missing("Olive Oil", "200 ml")])
        line_id = meal.lines[0].id
        with pytest.raises(UnitDimensionMismatchError):
            buy_missing_line(db_session, meal.id, line_id)
        db_session.rollback()
        db_session.refresh(oil)
        db_session.refresh(meal)
        assert Decimal(str(oil.quantity_base)) == Decimal("1")
        assert oil.version == 1
        assert [line.id for line in meal.lines] == [line_id]

    def test_count_must_be_whole(self, db_session: Session) -> None:
        meal = _meal(db_session, [_missing("eggs", "1.5 count")])
        with pytest.raises(NonIntegerCountError):
            buy_missing_line(db_session, meal.id, meal.lines[0].id)

    def test_rejects_a_tiny_mass_and_a_quantity_past_the_limit(self, db_session: Session) -> None:
        meal = _meal(db_session, [_missing("salt", None), _missing("flour", None)])
        salt, flour = meal.lines
        with pytest.raises(QuantityTooSmallError):
            buy_missing_line(db_session, meal.id, salt.id, quantity=Decimal("0.001"), unit=Unit.G)
        with pytest.raises(QuantityLimitError):
            buy_missing_line(
                db_session,
                meal.id,
                flour.id,
                quantity=Decimal("2000"),
                unit=Unit.KG,
            )

    def test_missing_meal_line_and_name(self, db_session: Session) -> None:
        meal = _meal(
            db_session,
            [
                MealLine(
                    kind="use",
                    item_name_snapshot="Leeks",
                    quantity_base=100,
                    dimension="mass",
                    display_unit="g",
                ),
                _missing("   ", None),
            ],
        )
        use_line, blank = meal.lines
        with pytest.raises(MealNotFoundError):
            buy_missing_line(db_session, "missing", use_line.id)
        with pytest.raises(MealLineNotFoundError):
            buy_missing_line(db_session, meal.id, "missing")
        with pytest.raises(MealLineNotFoundError):
            buy_missing_line(db_session, meal.id, use_line.id)
        with pytest.raises(MissingNameError):
            buy_missing_line(db_session, meal.id, blank.id, quantity=Decimal("1"), unit=Unit.COUNT)

    def test_buying_twice_does_not_add_twice(self, db_session: Session) -> None:
        meal = _meal(db_session, [_missing("butter", "200 g")])
        line_id = meal.lines[0].id
        buy_missing_line(db_session, meal.id, line_id)
        db_session.commit()
        with pytest.raises(MealLineNotFoundError):
            buy_missing_line(db_session, meal.id, line_id)
        db_session.rollback()
        item = ItemRepository(db_session).find_by_name_key("butter")
        assert item is not None
        assert Decimal(str(item.quantity_base)) == Decimal("200")
