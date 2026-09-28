from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.units import Unit


class MealLineRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: str
    item_id: str | None = None
    item_name: str
    quantity: Decimal | None = None
    unit: Unit | None = None
    missing_name: str | None = None
    missing_note: str | None = None
    position: int


class MealListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    sentence: str
    servings: int
    status: str
    cooked_at: str | None = None
    created_at: str
    use_count: int = 0
    missing_count: int = 0


class MealRead(MealListItem):
    steps: list[str] = Field(default_factory=list)
    lines: list[MealLineRead] = Field(default_factory=list)
    cook_session_id: str | None = None
