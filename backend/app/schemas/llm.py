from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.units import Dimension, Unit


class Constraints(BaseModel):
    """Output of parse_sentence."""

    model_config = ConfigDict(extra="forbid")

    must_use_item_ids: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)
    dietary: list[Literal["vegetarian", "vegan", "gluten_free", "dairy_free", "nut_free"]] = Field(
        default_factory=list
    )
    max_minutes: int | None = Field(default=None, ge=5, le=240)
    servings: int = Field(default=2, ge=1, le=24)
    mood: str | None = None
    free_text_notes: str | None = None


class ProposedUseLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["use"] = "use"
    item_id: str = Field(min_length=1)
    quantity: Decimal = Field(gt=0)
    unit: Unit


class ProposedMissingLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["missing"] = "missing"
    name: str = Field(min_length=1, max_length=80)
    quantity_note: str | None = Field(default=None, max_length=80)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Name must not be blank")
        return stripped


ProposedLine = Annotated[ProposedUseLine | ProposedMissingLine, Field(discriminator="kind")]


class MealProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=3, max_length=80)
    servings: int = Field(ge=1, le=24)
    lines: list[ProposedLine] = Field(min_length=1, max_length=20)
    steps: list[str] = Field(min_length=1, max_length=15)
    rationale: str | None = None

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 3:
            raise ValueError("Title must be at least 3 characters")
        return stripped

    @field_validator("steps")
    @classmethod
    def steps_not_blank(cls, steps: list[str]) -> list[str]:
        cleaned = [step.strip() for step in steps]
        if any(not step for step in cleaned):
            raise ValueError("Steps must not be blank")
        return cleaned


class PantryRow(BaseModel):
    """Compact pantry row carried in graph state and the proposal snapshot."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    quantity_base: Decimal
    dimension: Dimension
    display_unit: Unit
    expires_on: date | None = None
    version: int = Field(ge=1)


class Violation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    item_id: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


class Attempt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempt_no: int = Field(ge=1)
    trigger: Literal["initial", "auto_repair", "user_revision"]
    user_note: str | None = None
    proposal: dict[str, Any] | None = None
    validation_errors: list[dict[str, Any]] = Field(default_factory=list)


class GraphError(BaseModel):
    model_config = ConfigDict(extra="allow")

    code: str
    detail: str
    changed_item_ids: list[str] | None = None
    violations: list[dict[str, Any]] | None = None


class CommitResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meal_id: str
    title: str
