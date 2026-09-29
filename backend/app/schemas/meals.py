from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

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


class BuyMissingRequest(BaseModel):
    """Quantity for a shopping line that did not already name one.

    Omit both fields when the line already has a measure. Sending one without
    the other is rejected.
    """

    model_config = ConfigDict(extra="forbid")

    quantity: Decimal | None = Field(default=None, gt=0, le=1_000_000)
    unit: Unit | None = None

    @model_validator(mode="after")
    def quantity_with_unit(self) -> BuyMissingRequest:
        if (self.quantity is None) != (self.unit is None):
            raise ValueError("Send a quantity and a unit together.")
        if (
            self.unit == Unit.COUNT
            and self.quantity is not None
            and self.quantity != self.quantity.to_integral_value()
        ):
            raise ValueError("Counts must be whole numbers.")
        return self


class BoughtMissingRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meal: MealRead
    item_id: str
    item_name: str
    quantity: Decimal
    unit: Unit
    created: bool
