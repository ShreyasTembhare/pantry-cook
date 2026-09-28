"""Shared builders for cook tests."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from app.domain.units import Dimension, Unit
from app.schemas.llm import MealProposal, ProposedMissingLine, ProposedUseLine


def pantry_row(
    item_id: str,
    name: str,
    quantity_base: str,
    *,
    dimension: Dimension = Dimension.MASS,
    unit: Unit = Unit.G,
    expires_on: date | None = None,
    version: int = 1,
) -> dict[str, Any]:
    return {
        "id": item_id,
        "name": name,
        "quantity_base": quantity_base,
        "dimension": dimension.value,
        "display_unit": unit.value,
        "expires_on": expires_on.isoformat() if expires_on else None,
        "version": version,
    }


def use_line(item_id: str, quantity: str, unit: Unit = Unit.G) -> ProposedUseLine:
    return ProposedUseLine(item_id=item_id, quantity=Decimal(quantity), unit=unit)


def meal(
    *lines: ProposedUseLine | ProposedMissingLine,
    title: str = "Rice bowl",
    servings: int = 2,
) -> MealProposal:
    return MealProposal(
        title=title,
        servings=servings,
        lines=list(lines) or [ProposedMissingLine(name="olive oil", quantity_note="a splash")],
        steps=["Cook it."],
        rationale="A test proposal.",
    )


def soon(days: int = 1) -> date:
    return date.today() + timedelta(days=days)
