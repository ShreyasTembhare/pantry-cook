"""Undo puts back the quantities a cooked meal subtracted, once."""

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Item, Meal
from app.db.repositories import ItemRepository
from app.domain.commit import commit_cooked_meal, undo_cooked_meal
from app.domain.errors import (
    MealNotCookedError,
    MealNotFoundError,
    QuantityLimitError,
    UndoConflictError,
)
from app.domain.units import Unit
from app.schemas.items import ItemCreate
from tests.support import meal, pantry_row, use_line


def _item(db: Session, name: str, quantity: str, unit: Unit = Unit.G) -> Item:
    item = ItemRepository(db).create(ItemCreate(name=name, quantity=Decimal(quantity), unit=unit))
    db.commit()
    return item


def _cook(db: Session, item: Item, *lines: object, title: str = "Rice bowl") -> Meal:
    proposal = meal(*lines, title=title)  # type: ignore[arg-type]
    cooked = commit_cooked_meal(
        db,
        proposal=proposal,
        snapshot=[pantry_row(item.id, item.name, str(item.quantity_base), version=item.version)],
        sentence="cook it",
        cook_session_id=f"session-{item.id}",
    )
    db.commit()
    return cooked


class TestUndoCookedMeal:
    def test_restores_the_subtracted_base_quantity(self, db_session: Session) -> None:
        rice = _item(db_session, "Rice", "500")
        beans = _item(db_session, "Beans", "200")
        cooked = commit_cooked_meal(
            db_session,
            proposal=meal(
                use_line(rice.id, "200"),
                use_line(beans.id, "50"),
                title="Rice and beans",
            ),
            snapshot=[
                pantry_row(rice.id, "Rice", "500", version=rice.version),
                pantry_row(beans.id, "Beans", "200", version=beans.version),
            ],
            sentence="rice and beans",
            cook_session_id="session-restore",
        )
        db_session.commit()
        db_session.refresh(rice)
        assert Decimal(str(rice.quantity_base)) == Decimal("300")

        # Later pantry edits stay. Undo adds what the meal took, not the old total.
        rice.quantity_base = 100
        db_session.commit()

        undone = undo_cooked_meal(db_session, cooked.id)
        db_session.commit()

        db_session.refresh(rice)
        db_session.refresh(beans)
        assert undone.status == "undone"
        assert Decimal(str(rice.quantity_base)) == Decimal("300")
        assert rice.version == 3
        assert Decimal(str(beans.quantity_base)) == Decimal("200")
        assert beans.version == 3

    def test_sums_every_use_line_including_display_units(self, db_session: Session) -> None:
        flour = _item(db_session, "Flour", "1.5", Unit.KG)
        cooked = commit_cooked_meal(
            db_session,
            proposal=meal(
                use_line(flour.id, "0.2", Unit.KG),
                use_line(flour.id, "50", Unit.G),
                title="Flour dough",
            ),
            snapshot=[
                pantry_row(
                    flour.id,
                    "Flour",
                    "1500",
                    unit=Unit.KG,
                    version=flour.version,
                )
            ],
            sentence="dough",
            cook_session_id="session-flour",
        )
        db_session.commit()
        db_session.refresh(flour)
        assert Decimal(str(flour.quantity_base)) == Decimal("1250")

        undo_cooked_meal(db_session, cooked.id)
        db_session.commit()
        db_session.refresh(flour)
        assert Decimal(str(flour.quantity_base)) == Decimal("1500")

    def test_second_undo_does_not_restore_again(self, db_session: Session) -> None:
        rice = _item(db_session, "Rice", "500")
        cooked = _cook(db_session, rice, use_line(rice.id, "200"), title="Rice bowl")

        first = undo_cooked_meal(db_session, cooked.id)
        db_session.commit()
        db_session.refresh(rice)
        assert first.status == "undone"
        assert Decimal(str(rice.quantity_base)) == Decimal("500")
        version = rice.version

        second = undo_cooked_meal(db_session, cooked.id)
        db_session.commit()
        db_session.refresh(rice)
        assert second.status == "undone"
        assert Decimal(str(rice.quantity_base)) == Decimal("500")
        assert rice.version == version

    def test_conflict_rolls_back_the_whole_restore(self, db_session: Session) -> None:
        rice = _item(db_session, "Rice", "500")
        beans = _item(db_session, "Beans", "200")
        cooked = commit_cooked_meal(
            db_session,
            proposal=meal(use_line(rice.id, "200"), use_line(beans.id, "50"), title="Both"),
            snapshot=[
                pantry_row(rice.id, "Rice", "500", version=rice.version),
                pantry_row(beans.id, "Beans", "200", version=beans.version),
            ],
            sentence="both",
            cook_session_id="session-conflict",
        )
        db_session.commit()
        beans.dimension = "count"
        db_session.commit()

        with pytest.raises(UndoConflictError):
            undo_cooked_meal(db_session, cooked.id)
        db_session.rollback()

        db_session.refresh(rice)
        db_session.refresh(beans)
        meal_row = db_session.get(Meal, cooked.id)
        assert meal_row is not None
        assert meal_row.status == "cooked"
        assert Decimal(str(rice.quantity_base)) == Decimal("300")
        assert Decimal(str(beans.quantity_base)) == Decimal("150")

    def test_quantity_limit_leaves_the_meal_cooked(self, db_session: Session) -> None:
        rice = _item(db_session, "Rice", "500")
        cooked = _cook(db_session, rice, use_line(rice.id, "200"), title="Rice bowl")
        rice.quantity_base = 999_900
        db_session.commit()

        with pytest.raises(QuantityLimitError):
            undo_cooked_meal(db_session, cooked.id)
        db_session.rollback()

        db_session.refresh(rice)
        meal_row = db_session.get(Meal, cooked.id)
        assert meal_row is not None
        assert meal_row.status == "cooked"
        assert Decimal(str(rice.quantity_base)) == Decimal("999900")

    def test_deleted_item_is_recreated_from_the_snapshot(self, db_session: Session) -> None:
        rice = _item(db_session, "Rice", "500")
        cooked = _cook(db_session, rice, use_line(rice.id, "0.2", Unit.KG), title="Rice bowl")
        db_session.delete(rice)
        db_session.commit()
        db_session.expire_all()

        undone = undo_cooked_meal(db_session, cooked.id)
        db_session.commit()

        restored = db_session.execute(select(Item)).scalar_one()
        assert undone.status == "undone"
        assert restored.name == "Rice"
        assert restored.dimension == "mass"
        assert restored.display_unit == "kg"
        assert Decimal(str(restored.quantity_base)) == Decimal("200")

    def test_deleted_item_adds_onto_a_same_dimension_replacement(self, db_session: Session) -> None:
        rice = _item(db_session, "Rice", "500")
        cooked = _cook(db_session, rice, use_line(rice.id, "200"), title="Rice bowl")
        db_session.delete(rice)
        db_session.commit()
        replacement = _item(db_session, "rice", "100")
        db_session.expire_all()

        undo_cooked_meal(db_session, cooked.id)
        db_session.commit()

        rows = list(db_session.execute(select(Item)).scalars())
        assert len(rows) == 1
        assert rows[0].id == replacement.id
        assert Decimal(str(rows[0].quantity_base)) == Decimal("300")

    def test_deleted_item_with_a_different_measure_does_not_restore(
        self, db_session: Session
    ) -> None:
        rice = _item(db_session, "Rice", "500")
        cooked = _cook(db_session, rice, use_line(rice.id, "200"), title="Rice bowl")
        db_session.delete(rice)
        db_session.commit()
        replacement = _item(db_session, "Rice", "4", Unit.COUNT)
        db_session.expire_all()

        with pytest.raises(UndoConflictError):
            undo_cooked_meal(db_session, cooked.id)
        db_session.rollback()

        db_session.refresh(replacement)
        meal_row = db_session.get(Meal, cooked.id)
        assert meal_row is not None
        assert meal_row.status == "cooked"
        assert Decimal(str(replacement.quantity_base)) == Decimal("4")
        assert list(db_session.execute(select(Item)).scalars()) == [replacement]

    def test_proposed_meal_is_rejected(self, db_session: Session) -> None:
        rice = _item(db_session, "Rice", "500")
        cooked = _cook(db_session, rice, use_line(rice.id, "200"), title="Rice bowl")
        cooked.status = "proposed"
        db_session.commit()

        with pytest.raises(MealNotCookedError):
            undo_cooked_meal(db_session, cooked.id)
        db_session.rollback()

        db_session.refresh(rice)
        assert Decimal(str(rice.quantity_base)) == Decimal("300")

    def test_missing_meal(self, db_session: Session) -> None:
        with pytest.raises(MealNotFoundError):
            undo_cooked_meal(db_session, "missing")
