from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import event, select
from sqlalchemy.orm import Session, SessionTransaction

from app.db.models import CookSession, Item, Meal, MealLine
from app.domain.errors import (
    InsufficientQuantityError,
    MealNotCookedError,
    MealNotFoundError,
    QuantityLimitError,
    StaleProposalError,
    UndoConflictError,
)
from app.domain.units import MAX_BASE_QUANTITY, Dimension, Quantity, Unit
from app.schemas.items import normalise_name_key
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


class _Restore:
    __slots__ = ("amount", "dimension", "display_unit", "name")

    def __init__(
        self,
        amount: Decimal,
        dimension: Dimension,
        display_unit: Unit | None,
        name: str,
    ) -> None:
        self.amount = amount
        self.dimension = dimension
        self.display_unit = display_unit
        self.name = name


def undo_cooked_meal(db: Session, meal_id: str) -> Meal:
    """Add back each use line's stored base quantity and mark the meal undone.

    The caller owns ``commit()`` / ``rollback()``. A meal that is already
    ``undone`` is returned unchanged, and that check shares the immediate
    transaction with the quantity writes, so a second undo cannot restore twice.
    """
    _listen_immediate(db)
    meal = db.get(Meal, meal_id)
    if meal is None:
        raise MealNotFoundError(meal_id)
    if meal.status == "undone":
        return meal
    if meal.status != "cooked":
        raise MealNotCookedError(meal.status)

    live, orphans = _planned_restores(db, meal)
    _apply_restores(db, live, orphans)
    meal.status = "undone"
    db.flush()
    return meal


def _planned_restores(db: Session, meal: Meal) -> tuple[dict[str, _Restore], dict[str, _Restore]]:
    """Sum stored use-line amounts before any pantry row is written."""
    live: dict[str, _Restore] = {}
    orphans: dict[str, _Restore] = {}
    for line in meal.lines:
        if line.kind != "use" or line.quantity_base is None:
            continue
        amount = Decimal(str(line.quantity_base))
        if amount <= 0:
            continue
        dimension = _line_dimension(line)
        item = db.get(Item, line.item_id) if line.item_id else None
        if item is not None:
            _accumulate(live, item.id, amount, dimension, None, item.name)
            continue
        name = (line.item_name_snapshot or "").strip() or "Restored ingredient"
        _accumulate(
            orphans,
            normalise_name_key(name),
            amount,
            dimension,
            _line_display_unit(line, dimension),
            name,
        )
    return live, orphans


def _line_dimension(line: MealLine) -> Dimension:
    if not line.dimension:
        raise UndoConflictError("A use line is missing the measure needed to restore it.")
    try:
        return Dimension(line.dimension)
    except ValueError as exc:
        raise UndoConflictError("A use line has a measure this pantry cannot restore.") from exc


def _line_display_unit(line: MealLine, dimension: Dimension) -> Unit:
    raw = line.display_unit
    if raw:
        try:
            unit = Unit(raw)
        except ValueError:
            return _base_unit(dimension)
        if unit.dimension == dimension:
            return unit
    return _base_unit(dimension)


def _accumulate(
    bucket: dict[str, _Restore],
    key: str,
    amount: Decimal,
    dimension: Dimension,
    display_unit: Unit | None,
    name: str,
) -> None:
    current = bucket.get(key)
    if current is None:
        bucket[key] = _Restore(amount, dimension, display_unit, name)
        return
    if current.dimension != dimension:
        raise UndoConflictError(
            "This meal mixes measures for one ingredient, so it cannot be undone."
        )
    current.amount += amount


def _apply_restores(
    db: Session,
    live: dict[str, _Restore],
    orphans: dict[str, _Restore],
) -> None:
    additions: dict[str, Decimal] = {}

    def note(item: Item, amount: Decimal) -> None:
        additions[item.id] = additions.get(item.id, Decimal("0")) + amount

    for item_id, restore in live.items():
        item = db.get(Item, item_id)
        if item is None:
            raise UndoConflictError("A pantry item disappeared while this meal was being undone.")
        if item.dimension != restore.dimension.value:
            raise UndoConflictError(
                f"{item.name} is no longer measured the same way, so this meal cannot be undone."
            )
        note(item, restore.amount)

    creates: list[Item] = []
    for name_key, restore in orphans.items():
        existing = db.execute(select(Item).where(Item.name_key == name_key)).scalar_one_or_none()
        if existing is not None:
            if existing.dimension != restore.dimension.value:
                raise UndoConflictError(
                    f"{existing.name} is already in the pantry in a different measure."
                )
            note(existing, restore.amount)
            continue
        base_unit = _base_unit(restore.dimension)
        amount = Quantity(restore.amount, base_unit).amount
        if amount > MAX_BASE_QUANTITY:
            raise QuantityLimitError()
        unit = restore.display_unit or base_unit
        creates.append(
            Item(
                name=restore.name,
                name_key=name_key,
                quantity_base=float(amount),
                dimension=restore.dimension.value,
                display_unit=unit.value,
            )
        )

    projected: list[tuple[Item, Decimal]] = []
    for item_id, amount in additions.items():
        item = db.get(Item, item_id)
        if item is None:
            raise UndoConflictError("A pantry item disappeared while this meal was being undone.")
        projected.append((item, _projected(item, amount)))

    now = _now()
    for item, total in projected:
        item.quantity_base = float(total)
        item.version += 1
        item.updated_at = now
    for item in creates:
        db.add(item)


def _projected(item: Item, amount: Decimal) -> Decimal:
    base_unit = _base_unit(Dimension(item.dimension))
    total = Quantity(Decimal(str(item.quantity_base)), base_unit) + Quantity(amount, base_unit)
    if total.amount > MAX_BASE_QUANTITY:
        raise QuantityLimitError()
    return total.amount


def _base_unit(dimension: Dimension) -> Unit:
    if dimension == Dimension.MASS:
        return Unit.G
    if dimension == Dimension.VOLUME:
        return Unit.ML
    return Unit.COUNT
