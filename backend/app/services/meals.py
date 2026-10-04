"""Meal reads and the undo / bought writes shared with chat."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.repositories import MealRepository
from app.domain.buy import buy_missing_line
from app.domain.commit import undo_cooked_meal
from app.schemas.meals import BoughtMissingRead, BuyMissingRequest, MealListItem, MealRead
from app.services.reading import meal_to_list_item, meal_to_read


class MealService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.meals = MealRepository(db)

    def list(self, status: str | None = "cooked") -> list[MealListItem]:
        return [meal_to_list_item(meal) for meal in self.meals.list(status=status or None)]

    def get(self, meal_id: str) -> MealRead:
        return meal_to_read(self.meals.get(meal_id))

    def undo(self, meal_id: str) -> MealRead:
        try:
            meal = undo_cooked_meal(self.db, meal_id)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        self.db.refresh(meal)
        return meal_to_read(meal)

    def buy(self, meal_id: str, line_id: str, body: BuyMissingRequest) -> BoughtMissingRead:
        try:
            bought = buy_missing_line(
                self.db,
                meal_id,
                line_id,
                quantity=body.quantity,
                unit=body.unit,
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        self.db.refresh(bought.meal)
        self.db.refresh(bought.item)
        return BoughtMissingRead(
            meal=meal_to_read(bought.meal),
            item_id=bought.item.id,
            item_name=bought.item.name,
            quantity=bought.quantity.amount,
            unit=bought.quantity.unit,
            created=bought.created,
        )
