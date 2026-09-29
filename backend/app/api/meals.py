from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db.models import Meal, MealLine
from app.db.repositories import MealRepository
from app.domain.commit import undo_cooked_meal
from app.domain.units import Dimension, Quantity, Unit
from app.schemas.meals import MealLineRead, MealListItem, MealRead

router = APIRouter(prefix="/api/meals", tags=["meals"])


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


@router.get("", response_model=list[MealListItem])
def list_meals(
    status: str = "cooked",
    db: Session = Depends(get_db),  # noqa: B008
) -> list[MealListItem]:
    meals = MealRepository(db).list(status=status or None)
    return [meal_to_list_item(meal) for meal in meals]


@router.get("/{meal_id}", response_model=MealRead)
def get_meal(
    meal_id: str,
    db: Session = Depends(get_db),  # noqa: B008
) -> MealRead:
    meal = MealRepository(db).get(meal_id)
    return meal_to_read(meal)


@router.post("/{meal_id}/undo", response_model=MealRead)
def undo_meal(
    meal_id: str,
    db: Session = Depends(get_db),  # noqa: B008
) -> MealRead:
    """Restore subtracted quantities and mark the meal undone.

    Repeating the call returns the undone meal without adding the quantities again.
    """
    try:
        meal = undo_cooked_meal(db, meal_id)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(meal)
    return meal_to_read(meal)
