"""Turn ORM rows into the response models the API and chat share."""

from __future__ import annotations

from decimal import Decimal

from app.db.models import Item, Meal, MealLine
from app.domain.units import Dimension, Quantity, Unit
from app.schemas.items import ItemRead
from app.schemas.meals import MealLineRead, MealListItem, MealRead


def item_to_read(item: Item) -> ItemRead:
    display_qty = Quantity.from_base(
        item.quantity_base,
        Dimension(item.dimension),
        Unit(item.display_unit),
    )
    return ItemRead(
        id=item.id,
        name=item.name,
        quantity=display_qty.amount,
        unit=Unit(item.display_unit),
        dimension=Dimension(item.dimension),
        expires_on=item.expires_on,
        version=item.version,
        created_at=item.created_at.isoformat() if item.created_at else "",
        updated_at=item.updated_at.isoformat() if item.updated_at else "",
    )


def meal_to_list_item(meal: Meal) -> MealListItem:
    lines = list(meal.lines)
    return MealListItem(
        id=meal.id,
        title=meal.title,
        sentence=meal.sentence,
        servings=meal.servings,
        status=meal.status,
        cooked_at=meal.cooked_at.isoformat() if meal.cooked_at else None,
        created_at=meal.created_at.isoformat() if meal.created_at else "",
        use_count=sum(1 for line in lines if line.kind == "use"),
        missing_count=sum(1 for line in lines if line.kind == "missing"),
    )


def meal_line_to_read(line: MealLine) -> MealLineRead:
    quantity: Decimal | None = None
    unit: Unit | None = None
    if line.quantity_base is not None and line.dimension and line.display_unit:
        display = Quantity.from_base(
            line.quantity_base,
            Dimension(line.dimension),
            Unit(line.display_unit),
        )
        quantity = display.amount
        unit = Unit(line.display_unit)
    return MealLineRead(
        id=line.id,
        kind=line.kind,
        item_id=line.item_id,
        item_name=line.item_name_snapshot,
        quantity=quantity,
        unit=unit,
        missing_name=line.missing_name,
        missing_note=line.missing_note,
        position=line.position,
    )


def meal_to_read(meal: Meal) -> MealRead:
    summary = meal_to_list_item(meal)
    return MealRead(
        **summary.model_dump(),
        steps=list(meal.steps or []),
        lines=[meal_line_to_read(line) for line in meal.lines],
        cook_session_id=meal.cook_session_id,
    )
