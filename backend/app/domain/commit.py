from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import event, select
from sqlalchemy.orm import Session, SessionTransaction

from app.db.models import CookSession, Item, Meal, MealLine
from app.domain.errors import InsufficientQuantityError, StaleProposalError
from app.domain.units import Dimension, Quantity, Unit
from app.schemas.llm import MealProposal, PantryRow, ProposedMissingLine, ProposedUseLine


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _listen_immediate(db: Session) -> None:
    """Take a reserved SQLite lock before the version re-read.

    ``BEGIN IMMEDIATE`` makes the version check and the quantity write one
    critical section, so a second cook cannot commit against the same items
    in between. The listener is session-local and does not change other
    transactions.
    """
    if db.info.get("pantry_immediate"):
        return
    db.info["pantry_immediate"] = True

    def _on_begin(
        session: Session,
        transaction: SessionTransaction,
        connection: Any,
    ) -> None:
        del session
        if transaction.parent is not None:
            return
        if connection.dialect.name != "sqlite":
            return
        connection.exec_driver_sql("BEGIN IMMEDIATE")

    event.listen(db, "after_begin", _on_begin)


def commit_cooked_meal(
    db: Session,
    *,
    proposal: MealProposal | dict[str, Any],
    snapshot: list[PantryRow | dict[str, Any]],
    sentence: str,
    cook_session_id: str,
) -> Meal:
    """Insert a cooked meal and subtract use-lines in one transaction.

    The caller owns ``commit()`` / ``rollback()``. On stale versions or an
    over-consume, nothing is written and the exception propagates.
    """
    parsed = (
        proposal if isinstance(proposal, MealProposal) else MealProposal.model_validate(proposal)
    )
    rows = [
        row if isinstance(row, PantryRow) else PantryRow.model_validate(row) for row in snapshot
    ]
    snap_by_id = {row.id: row for row in rows}

    _listen_immediate(db)

    use_lines = [line for line in parsed.lines if isinstance(line, ProposedUseLine)]
    item_ids = list(dict.fromkeys(line.item_id for line in use_lines))
    items: dict[str, Item] = {}
    if item_ids:
        found = db.execute(select(Item).where(Item.id.in_(item_ids))).scalars().all()
        items = {item.id: item for item in found}

    changed: list[str] = []
    for item_id in item_ids:
        item = items.get(item_id)
        snap = snap_by_id.get(item_id)
        if item is None or snap is None or item.version != snap.version:
            changed.append(item_id)
    if changed:
        raise StaleProposalError(changed)

    requested: dict[str, Decimal] = {}
    for line in use_lines:
        item = items[line.item_id]
        if line.unit.dimension != Dimension(item.dimension):
            raise InsufficientQuantityError(item.id, str(line.quantity), str(item.quantity_base))
        requested[line.item_id] = (
            requested.get(line.item_id, Decimal("0"))
            + Quantity(line.quantity, line.unit).to_base().amount
        )

    for item_id, amount in requested.items():
        item = items[item_id]
        available = Quantity(
            Decimal(str(item.quantity_base)),
            Unit(item.display_unit).base_unit,
        ).amount
        if amount > available:
            raise InsufficientQuantityError(item_id, str(amount), str(available))
        base_unit = Unit(item.display_unit).base_unit
        remaining = Quantity(available - amount, base_unit)
        item.quantity_base = float(remaining.amount)
        item.version += 1
        item.updated_at = _now()

    now = _now()
    meal = Meal(
        sentence=sentence,
        title=parsed.title,
        servings=parsed.servings,
        steps=list(parsed.steps),
        status="cooked",
        cook_session_id=cook_session_id,
        cooked_at=now,
        created_at=now,
    )
    db.add(meal)
    db.flush()

    for position, line in enumerate(parsed.lines):
        if isinstance(line, ProposedUseLine):
            item = items[line.item_id]
            snap = snap_by_id.get(line.item_id)
            base_amount = Quantity(line.quantity, line.unit).to_base().amount
            db.add(
                MealLine(
                    meal_id=meal.id,
                    kind="use",
                    item_id=item.id,
                    item_name_snapshot=snap.name if snap is not None else item.name,
                    quantity_base=float(base_amount),
                    dimension=line.unit.dimension.value,
                    display_unit=line.unit.value,
                    position=position,
                )
            )
        elif isinstance(line, ProposedMissingLine):
            db.add(
                MealLine(
                    meal_id=meal.id,
                    kind="missing",
                    item_name_snapshot=line.name,
                    missing_name=line.name,
                    missing_note=line.quantity_note,
                    position=position,
                )
            )

    session_row = db.get(CookSession, cook_session_id)
    if session_row is not None:
        session_row.status = "committed"
        session_row.meal_id = meal.id
        session_row.updated_at = now

    db.flush()
    return meal
