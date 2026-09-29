"""Pydantic contracts for adding pantry items from one sentence."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from app.domain.units import Unit

UNREADABLE_SENTENCE = 'Couldn\'t read that as pantry items. Try "2 leeks and 500 g chicken".'


class SentenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sentence: str = Field(min_length=1, max_length=500)

    @field_validator("sentence")
    @classmethod
    def not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError('Say what to add, like "2 leeks and 500 g chicken".')
        return stripped


class DraftPantryLine(BaseModel):
    """One item the model claims the sentence named. The batch is validated together."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    quantity: Decimal = Field(gt=0, le=1_000_000)
    unit: Unit

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Name the item.")
        return stripped


class DraftPantrySentence(BaseModel):
    """Structured output for a quick-add sentence. Invalid output fails the whole call."""

    model_config = ConfigDict(extra="forbid")

    items: list[DraftPantryLine] = Field(min_length=1, max_length=20)


class ResolvedPantryLine(BaseModel):
    """A line that has passed unit rules and may be written."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    unit: Unit
    quantity: Decimal = Field(gt=0, le=1_000_000)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Name the item.")
        return stripped

    @field_validator("quantity")
    @classmethod
    def count_is_whole(cls, value: Decimal, info: ValidationInfo) -> Decimal:
        if info.data.get("unit") == Unit.COUNT and value != value.to_integral_value():
            raise ValueError("Counts must be whole numbers.")
        return value


class ResolvedPantryBatch(BaseModel):
    """The whole sentence, accepted or rejected together."""

    model_config = ConfigDict(extra="forbid")

    items: list[ResolvedPantryLine] = Field(min_length=1, max_length=20)


class PantrySentenceCommit(BaseModel):
    """The preview the user confirmed. Re-validated before any write."""

    model_config = ConfigDict(extra="forbid")

    items: list[DraftPantryLine] = Field(min_length=1, max_length=20)


class PantrySentencePreviewLine(BaseModel):
    name: str
    quantity: Decimal
    unit: Unit
    action: Literal["create", "add"]


class PantrySentencePreview(BaseModel):
    sentence: str
    items: list[PantrySentencePreviewLine]
