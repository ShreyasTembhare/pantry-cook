"""Sentence quick-add: one Pydantic batch, then a write, or neither."""

from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.db.repositories import ItemRepository
from app.domain.errors import (
    NonIntegerCountError,
    QuantityLimitError,
    QuantityTooSmallError,
    SentenceUnparsedError,
)
from app.domain.quick_add import (
    commit_parsed_items,
    normalise_draft,
    parse_pantry_sentence,
    preview_lines,
    rules_parse_sentence,
)
from app.domain.units import Unit
from app.graph.llm import FakeMealModel
from app.schemas.items import ItemCreate
from app.schemas.quick_add import UNREADABLE_SENTENCE, DraftPantryLine, DraftPantrySentence


def _names(sentence: str) -> list[tuple[str, Decimal, Unit]]:
    batch = parse_pantry_sentence(sentence, FakeMealModel())
    return [(line.name, line.quantity, line.unit) for line in batch.items]


class TestRulesParse:
    def test_leeks_and_chicken(self) -> None:
        assert _names("2 leeks and 500 g chicken") == [
            ("Leeks", Decimal("2"), Unit.COUNT),
            ("Chicken", Decimal("500.00"), Unit.G),
        ]

    def test_rice_eggs_and_cream(self) -> None:
        assert _names("2 kg rice, 6 eggs, 500 ml cream") == [
            ("Rice", Decimal("2.00"), Unit.KG),
            ("Eggs", Decimal("6"), Unit.COUNT),
            ("Cream", Decimal("500.00"), Unit.ML),
        ]

    def test_litres_and_of(self) -> None:
        parsed = rules_parse_sentence("1 L of milk and 250ml stock")
        assert [(line.name, line.unit) for line in parsed.items] == [
            ("Milk", Unit.L),
            ("Stock", Unit.ML),
        ]

    def test_same_dimension_math(self) -> None:
        batch = normalise_draft(rules_parse_sentence("500 g chicken and 1 kg chicken"))
        assert len(batch.items) == 1
        assert batch.items[0].unit == Unit.G
        assert batch.items[0].quantity == Decimal("1500.00")

    def test_volume_math_keeps_the_first_unit(self) -> None:
        batch = normalise_draft(rules_parse_sentence("1 L milk and 250 ml milk"))
        assert batch.items[0].unit == Unit.L
        assert batch.items[0].quantity == Decimal("1.25")

    def test_mixed_dimensions_reject_the_batch(self) -> None:
        draft = rules_parse_sentence("2 leeks and 500 g leeks")
        with pytest.raises(SentenceUnparsedError, match="Can't mix count and g"):
            normalise_draft(draft)

    def test_fractional_count_rejects_the_batch(self) -> None:
        draft = rules_parse_sentence("1.5 eggs and 500 g chicken")
        with pytest.raises(NonIntegerCountError):
            normalise_draft(draft)

    def test_tiny_mass_is_too_small(self) -> None:
        draft = rules_parse_sentence("0.001 g salt and 2 leeks")
        with pytest.raises(QuantityTooSmallError):
            normalise_draft(draft)

    def test_combined_mass_over_the_limit(self) -> None:
        draft = rules_parse_sentence("600 kg rice and 500000 g rice")
        with pytest.raises(QuantityLimitError):
            normalise_draft(draft)

    def test_unreadable_clause(self) -> None:
        with pytest.raises(SentenceUnparsedError, match='Couldn\'t read "hello"'):
            rules_parse_sentence("2 leeks and hello")

    def test_blank_sentence(self) -> None:
        with pytest.raises(SentenceUnparsedError) as caught:
            rules_parse_sentence("   ")
        assert caught.value.detail == UNREADABLE_SENTENCE

    def test_word_without_a_quantity(self) -> None:
        with pytest.raises(SentenceUnparsedError):
            parse_pantry_sentence("some rice", FakeMealModel())


class TestModelBoundary:
    def test_readable_sentence_stays_on_the_rules(self) -> None:
        model = FakeMealModel()
        batch = parse_pantry_sentence("6 eggs", model)
        assert batch.items[0].name == "Eggs"
        assert batch.items[0].unit == Unit.COUNT
        assert model.received == []

    def test_bad_model_output_is_a_clear_error(self) -> None:
        model = FakeMealModel(script=["not json"])
        with pytest.raises(SentenceUnparsedError) as caught:
            parse_pantry_sentence("something tasty please", model)
        assert caught.value.code == "sentence_unparsed"

    def test_scripted_batch_still_goes_through_pydantic(self) -> None:
        model = FakeMealModel(
            script=[
                DraftPantrySentence(
                    items=[
                        DraftPantryLine(name="Eggs", quantity=Decimal("1.5"), unit=Unit.COUNT),
                        DraftPantryLine(name="Chicken", quantity=Decimal("500"), unit=Unit.G),
                    ]
                )
            ]
        )
        with pytest.raises(NonIntegerCountError):
            parse_pantry_sentence("1.5 eggs and 500 g chicken", model)


class TestWrites:
    def test_commit_creates_every_line(self, db_session: Session) -> None:
        batch = parse_pantry_sentence("2 leeks and 500 g chicken", FakeMealModel())
        saved = commit_parsed_items(db_session, batch)
        db_session.commit()
        assert [item.name for item in saved] == ["Leeks", "Chicken"]
        chicken = ItemRepository(db_session).find_by_name_key("chicken")
        assert chicken is not None
        assert Decimal(str(chicken.quantity_base)) == Decimal("500")

    def test_preview_does_not_write(self, db_session: Session) -> None:
        batch = parse_pantry_sentence("2 leeks and 500 g chicken", FakeMealModel())
        preview = preview_lines(db_session, "2 leeks and 500 g chicken", batch)
        assert [line.action for line in preview.items] == ["create", "create"]
        assert ItemRepository(db_session).list() == []

    def test_same_dimension_adds_to_an_existing_item(self, db_session: Session) -> None:
        repo = ItemRepository(db_session)
        repo.create(ItemCreate(name="Chicken", quantity=Decimal("200"), unit=Unit.G))
        db_session.commit()
        batch = parse_pantry_sentence("500 g chicken and 2 leeks", FakeMealModel())
        preview = preview_lines(db_session, "500 g chicken and 2 leeks", batch)
        assert [(line.name, line.action) for line in preview.items] == [
            ("Chicken", "add"),
            ("Leeks", "create"),
        ]
        saved = commit_parsed_items(db_session, batch)
        db_session.commit()
        chicken = next(item for item in saved if item.name == "Chicken")
        assert Decimal(str(chicken.quantity_base)) == Decimal("700")

    def test_dimension_clash_writes_nothing(self, db_session: Session) -> None:
        repo = ItemRepository(db_session)
        repo.create(ItemCreate(name="Chicken", quantity=Decimal("2"), unit=Unit.COUNT))
        db_session.commit()
        batch = parse_pantry_sentence("2 leeks and 500 g chicken", FakeMealModel())
        with pytest.raises(SentenceUnparsedError, match="already stored as a count"):
            commit_parsed_items(db_session, batch)
        db_session.rollback()
        rows = repo.list()
        assert [row.name for row in rows] == ["Chicken"]
        assert Decimal(str(rows[0].quantity_base)) == Decimal("2")

    def test_bad_batch_is_not_committed(self, db_session: Session) -> None:
        draft = rules_parse_sentence("1.5 eggs and 500 g chicken")
        with pytest.raises(NonIntegerCountError):
            normalise_draft(draft)
        assert ItemRepository(db_session).list() == []
