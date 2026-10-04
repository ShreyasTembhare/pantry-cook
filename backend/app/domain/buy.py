"""Turn one missing meal line into a pantry item, then clear the line."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Item, Meal, MealLine
from app.db.repositories import ItemRepository
from app.domain.errors import (
    MealLineNotFoundError,
    MealNotFoundError,
    MissingNameError,
    NonIntegerCountError,
    QuantityLimitError,
    QuantityRequiredError,
    QuantityTooSmallError,
)
from app.domain.units import MAX_BASE_QUANTITY, MIN_POSITIVE_QUANTITY, Dimension, Quantity, Unit
from app.schemas.items import ItemCreate, normalise_name_key

# Longer units first so "kg" is not read as "g" and "ml" is not read as "l".
_NOTE_QUANTITY = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(kg|ml|count|g|l)\b",
    re.IGNORECASE,
)
_UNIT_FROM_NOTE = {
    "g": Unit.G,
    "kg": Unit.KG,
    "ml": Unit.ML,
    "l": Unit.L,
    "count": Unit.COUNT,
}


@dataclass(frozen=True, slots=True)
class BoughtLine:
    meal: Meal
    item: Item
    quantity: Quantity
    created: bool


def parse_quantity_note(note: str | None) -> tuple[Decimal, Unit] | None:
    """Pull a single amount and unit out of a shopping note.

    ``"about 200 g"`` is 200 g. ``"a splash"`` and notes with two measures
    (``"200 g or 1 kg"``) are not a quantity — the caller should ask.
    """
    if note is None or not note.strip():
        return None
    matches = list(_NOTE_QUANTITY.finditer(note))
    if len(matches) != 1:
        return None
    raw_amount, raw_unit = matches[0].group(1), matches[0].group(2)
    try:
        amount = Decimal(raw_amount.replace(",", "."))
    except InvalidOperation:
        return None
    if amount <= 0:
        return None
    return amount, _UNIT_FROM_NOTE[raw_unit.casefold()]


def buy_missing_line(
    db: Session,
    meal_id: str,
    line_id: str,
    *,
    quantity: Decimal | None = None,
    unit: Unit | None = None,
) -> BoughtLine:
    """Create or increment the pantry item named by a missing line, then drop it.

    The caller owns ``commit()`` / ``rollback()``. An explicit quantity wins.
    Otherwise the line's stored measure is used, then a quantity parsed from
    its note. If none of those exist, ``QuantityRequiredError`` is raised and
    the line stays.
    """
    meal = db.execute(select(Meal).where(Meal.id == meal_id).with_for_update()).scalar_one_or_none()
    if meal is None:
        raise MealNotFoundError(meal_id)
    line = next(
        (row for row in meal.lines if row.id == line_id and row.kind == "missing"),
        None,
    )
    if line is None:
        raise MealLineNotFoundError(line_id)

    measured = _resolve_quantity(line, quantity, unit)
    name = _line_name(line)
    if not name:
        raise MissingNameError()

    repo = ItemRepository(db)
    existing = repo.find_by_name_key(normalise_name_key(name), lock=True)
    if existing is None:
        item = repo.create(ItemCreate(name=name, quantity=measured.amount, unit=measured.unit))
        created = True
    else:
        item = repo.add_quantity(existing.id, measured.amount, measured.unit)
        created = False

    meal.lines.remove(line)
    db.flush()
    return BoughtLine(meal=meal, item=item, quantity=measured, created=created)


def _resolve_quantity(
    line: MealLine,
    quantity: Decimal | None,
    unit: Unit | None,
) -> Quantity:
    if quantity is not None and unit is not None:
        return _checked_quantity(quantity, unit)
    stored = _stored_quantity(line)
    if stored is not None:
        return _checked_quantity(stored[0], stored[1])
    parsed = parse_quantity_note(line.missing_note)
    if parsed is None:
        raise QuantityRequiredError()
    return _checked_quantity(parsed[0], parsed[1])


def _stored_quantity(line: MealLine) -> tuple[Decimal, Unit] | None:
    if line.quantity_base is None or not line.dimension or not line.display_unit:
        return None
    try:
        dimension = Dimension(line.dimension)
        unit = Unit(line.display_unit)
    except ValueError:
        return None
    if unit.dimension != dimension:
        return None
    amount = Decimal(str(line.quantity_base))
    if amount <= 0:
        return None
    display = Quantity.from_base(amount, dimension, unit)
    if display.amount <= 0:
        return None
    return display.amount, unit


def _checked_quantity(amount: Decimal, unit: Unit) -> Quantity:
    if unit == Unit.COUNT and amount != amount.to_integral_value():
        raise NonIntegerCountError()
    if amount <= 0:
        raise QuantityRequiredError()
    measured = Quantity(amount, unit)
    if measured.amount <= 0 or (
        unit != Unit.COUNT and measured.to_base().amount < MIN_POSITIVE_QUANTITY
    ):
        raise QuantityTooSmallError()
    if measured.to_base().amount > MAX_BASE_QUANTITY:
        raise QuantityLimitError()
    return measured


def _line_name(line: MealLine) -> str:
    raw = line.missing_name or line.item_name_snapshot or ""
    return re.sub(r"\s+", " ", raw).strip()
