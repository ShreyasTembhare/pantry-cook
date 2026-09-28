from __future__ import annotations

import re
import unicodedata
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.units import Dimension, Unit


def normalise_name_key(name: str) -> str:
    """Casefold + NFKC normalise + collapse whitespace for duplicate detection."""
    normalised = unicodedata.normalize("NFKC", name.casefold())
    return re.sub(r"\s+", " ", normalised).strip()


class ItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    quantity: Decimal = Field(ge=0, le=1_000_000)
    unit: Unit
    expires_on: date | None = None

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Name must not be blank")
        return v.strip()

    @field_validator("quantity")
    @classmethod
    def count_must_be_integer(cls, v: Decimal, info: object) -> Decimal:
        return v


class ItemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    quantity: Decimal | None = Field(default=None, ge=0, le=1_000_000)
    unit: Unit | None = None
    expires_on: date | None = None
    version: int = Field(ge=1, description="Optimistic lock version for conflict detection")

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("Name must not be blank")
        return v.strip() if v else v


class ItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    quantity: Decimal
    unit: Unit
    dimension: Dimension
    expires_on: date | None
    version: int
    created_at: str
    updated_at: str
