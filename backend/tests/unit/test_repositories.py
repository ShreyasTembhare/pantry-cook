"""Tests for ItemRepository — CRUD, uniqueness, versioning."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.db.repositories import ItemRepository
from app.domain.errors import DuplicateItemError, ItemNotFoundError, StaleVersionError
from app.domain.units import Unit
from app.schemas.items import ItemCreate, ItemUpdate


class TestItemRepositoryCreate:
    def test_create_basic(self, db_session: Session) -> None:
        repo = ItemRepository(db_session)
        item = repo.create(ItemCreate(name="Rice", quantity=Decimal("500"), unit=Unit.G))
        db_session.commit()

        assert item.id is not None
        assert item.name == "Rice"
        assert item.name_key == "rice"
        assert item.quantity_base == 500.0
        assert item.dimension == "mass"
        assert item.display_unit == "g"
        assert item.version == 1

    def test_create_with_kg(self, db_session: Session) -> None:
        repo = ItemRepository(db_session)
        item = repo.create(ItemCreate(name="Flour", quantity=Decimal("1.5"), unit=Unit.KG))
        db_session.commit()

        assert item.quantity_base == 1500.0
        assert item.display_unit == "kg"

    def test_create_with_expiry(self, db_session: Session) -> None:
        repo = ItemRepository(db_session)
        item = repo.create(
            ItemCreate(
                name="Milk",
                quantity=Decimal("1"),
                unit=Unit.L,
                expires_on=date(2025, 3, 15),
            )
        )
        db_session.commit()

        assert item.expires_on == date(2025, 3, 15)

    def test_duplicate_name_rejected(self, db_session: Session) -> None:
        repo = ItemRepository(db_session)
        repo.create(ItemCreate(name="Rice", quantity=Decimal("500"), unit=Unit.G))
        db_session.commit()

        with pytest.raises(DuplicateItemError) as exc_info:
            repo.create(ItemCreate(name="rice", quantity=Decimal("200"), unit=Unit.G))

        assert exc_info.value.code == "duplicate_item"

    def test_duplicate_normalised(self, db_session: Session) -> None:
        repo = ItemRepository(db_session)
        repo.create(ItemCreate(name="Brown Rice", quantity=Decimal("500"), unit=Unit.G))
        db_session.commit()

        with pytest.raises(DuplicateItemError):
            repo.create(ItemCreate(name="brown  rice", quantity=Decimal("200"), unit=Unit.G))

    def test_zero_quantity(self, db_session: Session) -> None:
        repo = ItemRepository(db_session)
        item = repo.create(ItemCreate(name="Salt", quantity=Decimal("0"), unit=Unit.G))
        db_session.commit()

        assert item.quantity_base == 0.0


class TestItemRepositoryGet:
    def test_get_existing(self, db_session: Session) -> None:
        repo = ItemRepository(db_session)
        created = repo.create(ItemCreate(name="Rice", quantity=Decimal("500"), unit=Unit.G))
        db_session.commit()

        fetched = repo.get(created.id)
        assert fetched.name == "Rice"

    def test_get_missing_raises(self, db_session: Session) -> None:
        repo = ItemRepository(db_session)
        with pytest.raises(ItemNotFoundError):
            repo.get("nonexistent-id")


class TestItemRepositoryList:
    def test_list_empty(self, db_session: Session) -> None:
        repo = ItemRepository(db_session)
        assert repo.list() == []

    def test_list_sorted_by_expiry(self, db_session: Session) -> None:
        repo = ItemRepository(db_session)
        repo.create(
            ItemCreate(
                name="Milk", quantity=Decimal("1"), unit=Unit.L, expires_on=date(2025, 3, 20)
            )
        )
        repo.create(
            ItemCreate(
                name="Eggs", quantity=Decimal("6"), unit=Unit.COUNT, expires_on=date(2025, 3, 15)
            )
        )
        repo.create(ItemCreate(name="Rice", quantity=Decimal("1"), unit=Unit.KG))
        db_session.commit()

        items = repo.list(sort_by="expires_on")
        names = [i.name for i in items]
        assert names == ["Eggs", "Milk", "Rice"]

    def test_list_sorted_by_name(self, db_session: Session) -> None:
        repo = ItemRepository(db_session)
        repo.create(ItemCreate(name="Zucchini", quantity=Decimal("2"), unit=Unit.COUNT))
        repo.create(ItemCreate(name="Apple", quantity=Decimal("3"), unit=Unit.COUNT))
        db_session.commit()

        items = repo.list(sort_by="name")
        assert items[0].name == "Apple"
        assert items[1].name == "Zucchini"


class TestItemRepositoryUpdate:
    def test_update_name(self, db_session: Session) -> None:
        repo = ItemRepository(db_session)
        item = repo.create(ItemCreate(name="Rice", quantity=Decimal("500"), unit=Unit.G))
        db_session.commit()

        updated = repo.update(item.id, ItemUpdate(name="Brown Rice", version=1))
        db_session.commit()

        assert updated.name == "Brown Rice"
        assert updated.name_key == "brown rice"
        assert updated.version == 2

    def test_update_quantity(self, db_session: Session) -> None:
        repo = ItemRepository(db_session)
        item = repo.create(ItemCreate(name="Rice", quantity=Decimal("500"), unit=Unit.G))
        db_session.commit()

        updated = repo.update(item.id, ItemUpdate(quantity=Decimal("300"), version=1))
        db_session.commit()

        assert updated.quantity_base == 300.0
        assert updated.version == 2

    def test_update_unit_converts(self, db_session: Session) -> None:
        repo = ItemRepository(db_session)
        item = repo.create(ItemCreate(name="Flour", quantity=Decimal("500"), unit=Unit.G))
        db_session.commit()

        updated = repo.update(item.id, ItemUpdate(quantity=Decimal("1.5"), unit=Unit.KG, version=1))
        db_session.commit()

        assert updated.quantity_base == 1500.0
        assert updated.display_unit == "kg"

    def test_stale_version_rejected(self, db_session: Session) -> None:
        repo = ItemRepository(db_session)
        item = repo.create(ItemCreate(name="Rice", quantity=Decimal("500"), unit=Unit.G))
        db_session.commit()

        repo.update(item.id, ItemUpdate(name="Brown Rice", version=1))
        db_session.commit()

        with pytest.raises(StaleVersionError) as exc_info:
            repo.update(item.id, ItemUpdate(name="White Rice", version=1))

        assert exc_info.value.code == "stale_version"

    def test_clear_expiry_when_field_is_sent(self, db_session: Session) -> None:
        repo = ItemRepository(db_session)
        item = repo.create(
            ItemCreate(
                name="Milk",
                quantity=Decimal("1"),
                unit=Unit.L,
                expires_on=date(2026, 10, 2),
            )
        )
        db_session.commit()

        renamed = repo.update(item.id, ItemUpdate(name="Whole milk", version=1))
        db_session.commit()
        assert renamed.expires_on == date(2026, 10, 2)

        cleared = repo.update(item.id, ItemUpdate(expires_on=None, version=2))
        db_session.commit()
        assert cleared.expires_on is None

    def test_rename_to_duplicate_rejected(self, db_session: Session) -> None:
        repo = ItemRepository(db_session)
        repo.create(ItemCreate(name="Rice", quantity=Decimal("500"), unit=Unit.G))
        item2 = repo.create(ItemCreate(name="Flour", quantity=Decimal("1"), unit=Unit.KG))
        db_session.commit()

        with pytest.raises(DuplicateItemError):
            repo.update(item2.id, ItemUpdate(name="Rice", version=1))


class TestItemRepositoryDelete:
    def test_delete(self, db_session: Session) -> None:
        repo = ItemRepository(db_session)
        item = repo.create(ItemCreate(name="Rice", quantity=Decimal("500"), unit=Unit.G))
        db_session.commit()

        repo.delete(item.id)
        db_session.commit()

        with pytest.raises(ItemNotFoundError):
            repo.get(item.id)

    def test_delete_missing_raises(self, db_session: Session) -> None:
        repo = ItemRepository(db_session)
        with pytest.raises(ItemNotFoundError):
            repo.delete("nonexistent")
