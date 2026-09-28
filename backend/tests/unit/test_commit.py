"""Atomic meal commit: subtract, stale detection, full consumption, missing lines."""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Item, Meal, MealLine
from app.db.repositories import ItemRepository
from app.domain.commit import commit_cooked_meal
from app.domain.errors import InsufficientQuantityError, StaleProposalError
from app.domain.units import Unit
from app.schemas.items import ItemCreate
from app.schemas.llm import ProposedMissingLine
from tests.support import meal, pantry_row, use_line


def _rice(db: Session, quantity: str = "500") -> Item:
    item = ItemRepository(db).create(
        ItemCreate(name="Rice", quantity=Decimal(quantity), unit=Unit.G)
    )
    db.commit()
    return item


class TestCommitMeal:
    def test_happy_path_subtracts_and_keeps_missing_lines(self, db_session: Session) -> None:
        rice = _rice(db_session)
        beans = ItemRepository(db_session).create(
            ItemCreate(name="Beans", quantity=Decimal("200"), unit=Unit.G)
        )
        db_session.commit()
        proposal = meal(
            use_line(rice.id, "200"),
            ProposedMissingLine(name="olive oil", quantity_note="a splash"),
            title="Rice and oil",
        )
        snapshot = [
            pantry_row(rice.id, "Rice", "500", version=rice.version),
            pantry_row(beans.id, "Beans", "200", version=beans.version),
        ]

        cooked = commit_cooked_meal(
            db_session,
            proposal=proposal,
            snapshot=snapshot,
            sentence="rice please",
            cook_session_id="session-1",
        )
        db_session.commit()

        db_session.refresh(rice)
        assert Decimal(str(rice.quantity_base)) == Decimal("300")
        assert rice.version == 2
        assert cooked.status == "cooked"
        kinds = [line.kind for line in cooked.lines]
        assert kinds == ["use", "missing"]
        missing = cooked.lines[1]
        assert missing.missing_name == "olive oil"
        assert missing.missing_note == "a splash"
        # An unrelated item is not touched.
        db_session.refresh(beans)
        assert beans.version == 1
        assert Decimal(str(beans.quantity_base)) == Decimal("200")

    def test_insufficient_quantity_rolls_back(self, db_session: Session) -> None:
        rice = _rice(db_session, "100")
        proposal = meal(use_line(rice.id, "250"), title="Too much rice")
        snapshot = [pantry_row(rice.id, "Rice", "100", version=rice.version)]

        try:
            commit_cooked_meal(
                db_session,
                proposal=proposal,
                snapshot=snapshot,
                sentence="a mountain of rice",
                cook_session_id="session-2",
            )
            db_session.commit()
            raise AssertionError("expected insufficient quantity")
        except InsufficientQuantityError:
            db_session.rollback()

        db_session.refresh(rice)
        assert Decimal(str(rice.quantity_base)) == Decimal("100")
        assert db_session.execute(select(Meal)).scalars().all() == []

    def test_stale_version_leaves_pantry_unchanged(self, db_session: Session) -> None:
        rice = _rice(db_session)
        snapshot = [pantry_row(rice.id, "Rice", "500", version=rice.version)]
        rice.version = 4
        db_session.commit()
        proposal = meal(use_line(rice.id, "100"), title="Stale rice")

        try:
            commit_cooked_meal(
                db_session,
                proposal=proposal,
                snapshot=snapshot,
                sentence="rice",
                cook_session_id="session-3",
            )
            raise AssertionError("expected stale proposal")
        except StaleProposalError as exc:
            db_session.rollback()
            assert exc.changed_item_ids == [rice.id]

        db_session.refresh(rice)
        assert Decimal(str(rice.quantity_base)) == Decimal("500")
        assert rice.version == 4
        assert db_session.execute(select(Meal)).scalars().all() == []

    def test_fully_consumed_stays_at_zero(self, db_session: Session) -> None:
        rice = _rice(db_session, "200")
        proposal = meal(use_line(rice.id, "200"), title="Finish the rice")
        snapshot = [pantry_row(rice.id, "Rice", "200", version=1)]

        commit_cooked_meal(
            db_session,
            proposal=proposal,
            snapshot=snapshot,
            sentence="use the rice",
            cook_session_id="session-4",
        )
        db_session.commit()

        db_session.refresh(rice)
        assert Decimal(str(rice.quantity_base)) == Decimal("0")
        assert db_session.get(Item, rice.id) is not None

    def test_unrelated_version_change_does_not_stale(self, db_session: Session) -> None:
        rice = _rice(db_session)
        salt = ItemRepository(db_session).create(
            ItemCreate(name="Salt", quantity=Decimal("0"), unit=Unit.G)
        )
        db_session.commit()
        salt.version = 9
        db_session.commit()
        proposal = meal(use_line(rice.id, "50"), title="Rice with salt nearby")
        snapshot = [
            pantry_row(rice.id, "Rice", "500", version=rice.version),
            pantry_row(salt.id, "Salt", "0", version=1),
        ]

        commit_cooked_meal(
            db_session,
            proposal=proposal,
            snapshot=snapshot,
            sentence="rice",
            cook_session_id="session-5",
        )
        db_session.commit()
        db_session.refresh(rice)
        assert Decimal(str(rice.quantity_base)) == Decimal("450")

    def test_deleting_item_keeps_the_snapshot_name(self, db_session: Session) -> None:
        rice = _rice(db_session)
        proposal = meal(use_line(rice.id, "50"), title="Rice bowl")
        commit_cooked_meal(
            db_session,
            proposal=proposal,
            snapshot=[pantry_row(rice.id, "Rice", "500", version=rice.version)],
            sentence="rice",
            cook_session_id="session-6",
        )
        db_session.commit()
        db_session.delete(rice)
        db_session.commit()

        line = db_session.execute(select(MealLine)).scalar_one()
        db_session.refresh(line)
        assert line.item_id is None
        assert line.item_name_snapshot == "Rice"
