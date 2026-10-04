from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import asc, desc, func, nullslast, select
from sqlalchemy.orm import Session

from app.db.models import CookSession, Item, Meal
from app.domain.errors import (
    DuplicateItemError,
    ItemNotFoundError,
    MealNotFoundError,
    QuantityLimitError,
    SessionNotFoundError,
    StaleVersionError,
    UnitDimensionMismatchError,
)
from app.domain.units import MAX_BASE_QUANTITY, Dimension, Quantity, Unit
from app.schemas.items import ItemCreate, ItemUpdate, normalise_name_key


class ItemRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def create(self, data: ItemCreate) -> Item:
        name_key = normalise_name_key(data.name)

        existing = self._db.execute(
            select(Item).where(Item.name_key == name_key)
        ).scalar_one_or_none()
        if existing:
            raise DuplicateItemError(data.name, existing.id)

        qty = Quantity(data.quantity, data.unit)
        base = qty.to_base()

        item = Item(
            name=data.name,
            name_key=name_key,
            quantity_base=float(base.amount),
            dimension=data.unit.dimension.value,
            display_unit=data.unit.value,
            expires_on=data.expires_on,
        )
        self._db.add(item)
        self._db.flush()
        return item

    def get(self, item_id: str) -> Item:
        item = self._db.get(Item, item_id)
        if item is None:
            raise ItemNotFoundError(item_id)
        return item

    def find_by_name_key(self, name_key: str, *, lock: bool = False) -> Item | None:
        stmt = select(Item).where(Item.name_key == name_key)
        if lock:
            stmt = stmt.with_for_update()
        return self._db.execute(stmt).scalar_one_or_none()

    def list(
        self,
        sort_by: str = "expires_on",
        soon_within_days: int | None = None,
    ) -> list[Item]:
        stmt = select(Item)

        if sort_by == "expires_on":
            stmt = stmt.order_by(
                nullslast(asc(Item.expires_on)),
                asc(Item.name),
            )
        elif sort_by == "name":
            stmt = stmt.order_by(asc(Item.name))
        elif sort_by == "created_at":
            stmt = stmt.order_by(asc(Item.created_at))
        else:
            stmt = stmt.order_by(
                nullslast(asc(Item.expires_on)),
                asc(Item.name),
            )

        result = self._db.execute(stmt).scalars().all()
        return list(result)

    def update(self, item_id: str, data: ItemUpdate) -> Item:
        item = self.get(item_id)

        if item.version != data.version:
            raise StaleVersionError(item_id, data.version, item.version)

        if data.name is not None:
            new_key = normalise_name_key(data.name)
            if new_key != item.name_key:
                existing = self._db.execute(
                    select(Item).where(Item.name_key == new_key, Item.id != item_id)
                ).scalar_one_or_none()
                if existing:
                    raise DuplicateItemError(data.name, existing.id)
            item.name = data.name
            item.name_key = new_key

        if data.quantity is not None or data.unit is not None:
            unit = data.unit or Unit(item.display_unit)
            quantity = (
                data.quantity
                if data.quantity is not None
                else Quantity.from_base(
                    item.quantity_base,
                    Dimension(item.dimension),
                    Unit(item.display_unit),
                ).amount
            )

            qty = Quantity(quantity, unit)
            base = qty.to_base()
            item.quantity_base = float(base.amount)
            item.dimension = unit.dimension.value
            item.display_unit = unit.value

        if "expires_on" in data.model_fields_set:
            item.expires_on = data.expires_on

        item.version += 1
        self._db.flush()
        return item

    def delete(self, item_id: str) -> None:
        item = self.get(item_id)
        self._db.delete(item)
        self._db.flush()

    def add_quantity(self, item_id: str, quantity: Decimal, unit: Unit) -> Item:
        """Add ``quantity`` onto an existing item when the dimension matches."""
        item = self.get(item_id)
        incoming = Quantity(quantity, unit)
        if incoming.dimension.value != item.dimension:
            raise UnitDimensionMismatchError(item.dimension, incoming.dimension.value)
        current = Quantity(Decimal(str(item.quantity_base)), unit.base_unit)
        total = current + incoming.to_base()
        if total.amount > MAX_BASE_QUANTITY:
            raise QuantityLimitError()
        item.quantity_base = float(total.amount)
        item.version += 1
        self._db.flush()
        return item

    def _to_display_quantity(self, item: Item) -> Quantity:
        return Quantity.from_base(
            item.quantity_base,
            Dimension(item.dimension),
            Unit(item.display_unit),
        )


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class MealRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def list(self, status: str | None = "cooked") -> list[Meal]:
        stmt = select(Meal).order_by(desc(Meal.created_at), desc(Meal.id))
        if status:
            stmt = stmt.where(Meal.status == status)
        return list(self._db.execute(stmt).scalars().all())

    def get(self, meal_id: str) -> Meal:
        meal = self._db.get(Meal, meal_id)
        if meal is None:
            raise MealNotFoundError(meal_id)
        return meal


class CookSessionRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def create(self, sentence: str) -> CookSession:
        now = _now()
        row = CookSession(
            sentence=sentence,
            status="running",
            attempt_count=0,
            created_at=now,
            updated_at=now,
            expires_at=now + timedelta(hours=24),
        )
        self._db.add(row)
        self._db.flush()
        return row

    def get(self, session_id: str) -> CookSession:
        row = self._db.get(CookSession, session_id)
        if row is None:
            raise SessionNotFoundError(session_id)
        return row

    def list(self, status: str) -> list[CookSession]:
        stmt = (
            select(CookSession)
            .where(CookSession.status == status)
            .order_by(desc(CookSession.updated_at), desc(CookSession.id))
        )
        return list(self._db.execute(stmt).scalars().all())

    def list_finished_before(self, before: datetime) -> list[CookSession]:
        stmt = (
            select(CookSession)
            .where(
                CookSession.status.in_(("abandoned", "committed", "failed")),
                CookSession.updated_at <= before,
            )
            .order_by(asc(CookSession.updated_at), asc(CookSession.id))
        )
        return list(self._db.execute(stmt).scalars().all())

    def count_status(self, status: str) -> int:
        stmt = select(func.count()).select_from(CookSession).where(CookSession.status == status)
        return int(self._db.execute(stmt).scalar_one())

    def touch(self, row: CookSession) -> CookSession:
        row.updated_at = _now()
        self._db.flush()
        return row
