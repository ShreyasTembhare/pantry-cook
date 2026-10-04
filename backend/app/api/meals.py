from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.error_handlers import problem_responses
from app.schemas.meals import BoughtMissingRead, BuyMissingRequest, MealListItem, MealRead
from app.services.meals import MealService

router = APIRouter(prefix="/api/meals", tags=["meals"])


@router.get("", response_model=list[MealListItem], responses=problem_responses(422))
def list_meals(
    status: Literal["proposed", "cooked", "undone"] = "cooked",
    db: Session = Depends(get_db),  # noqa: B008
) -> list[MealListItem]:
    return MealService(db).list(status)


@router.get("/{meal_id}", response_model=MealRead, responses=problem_responses(404))
def get_meal(
    meal_id: str,
    db: Session = Depends(get_db),  # noqa: B008
) -> MealRead:
    return MealService(db).get(meal_id)


@router.post("/{meal_id}/undo", response_model=MealRead, responses=problem_responses(404, 409, 422))
def undo_meal(
    meal_id: str,
    db: Session = Depends(get_db),  # noqa: B008
) -> MealRead:
    """Restore subtracted quantities and mark the meal undone.

    Repeating the call returns the undone meal without adding the quantities again.
    """
    return MealService(db).undo(meal_id)


@router.post(
    "/{meal_id}/lines/{line_id}/bought",
    response_model=BoughtMissingRead,
    responses=problem_responses(404, 409, 422),
)
def buy_meal_line(
    meal_id: str,
    line_id: str,
    body: BuyMissingRequest = Body(default_factory=BuyMissingRequest),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
) -> BoughtMissingRead:
    """Add the missing ingredient to the pantry and drop it from the shopping list.

    Send a quantity and unit when the line does not already have one.
    """
    return MealService(db).buy(meal_id, line_id, body)
