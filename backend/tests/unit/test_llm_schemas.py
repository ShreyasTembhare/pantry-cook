"""Meal proposal and cook request contracts."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.domain.units import Unit
from app.schemas.cook import CookConfirmRequest, CookReviseRequest, CookStartRequest, ResumePayload
from app.schemas.llm import Constraints, MealProposal, ProposedMissingLine, ProposedUseLine


class TestMealProposal:
    def test_accepts_use_and_missing_lines(self) -> None:
        proposal = MealProposal(
            title="Leek skillet",
            servings=2,
            lines=[
                ProposedUseLine(item_id="leeks", quantity=Decimal("150"), unit=Unit.G),
                ProposedMissingLine(name="olive oil", quantity_note="a splash"),
            ],
            steps=["Cook the leeks."],
            rationale="Uses the leeks before Thursday.",
        )
        assert proposal.lines[0].kind == "use"
        assert proposal.lines[1].kind == "missing"

    def test_rejects_extra_fields(self) -> None:
        with pytest.raises(ValidationError):
            MealProposal(
                title="Leek skillet",
                servings=2,
                lines=[ProposedMissingLine(name="olive oil")],
                steps=["Cook."],
                surprise=True,  # type: ignore[call-arg]
            )

    def test_rejects_empty_lines(self) -> None:
        with pytest.raises(ValidationError):
            MealProposal(title="Leek skillet", servings=2, lines=[], steps=["Cook."])

    def test_rejects_servings_out_of_range(self) -> None:
        with pytest.raises(ValidationError):
            MealProposal(
                title="Leek skillet",
                servings=0,
                lines=[ProposedMissingLine(name="olive oil")],
                steps=["Cook."],
            )
        with pytest.raises(ValidationError):
            MealProposal(
                title="Leek skillet",
                servings=25,
                lines=[ProposedMissingLine(name="olive oil")],
                steps=["Cook."],
            )

    def test_rejects_non_positive_quantity(self) -> None:
        with pytest.raises(ValidationError):
            ProposedUseLine(item_id="rice", quantity=Decimal("0"), unit=Unit.G)
        with pytest.raises(ValidationError):
            ProposedUseLine(item_id="rice", quantity=Decimal("-1"), unit=Unit.G)


class TestConstraints:
    def test_defaults(self) -> None:
        constraints = Constraints()
        assert constraints.servings == 2
        assert constraints.must_use_item_ids == []
        assert constraints.dietary == []
        assert constraints.max_minutes is None


class TestCookRequests:
    def test_sentence_bounds(self) -> None:
        assert CookStartRequest(sentence="food").sentence == "food"
        assert CookStartRequest(sentence="").sentence == ""
        assert CookStartRequest(sentence="   ").sentence == ""
        with pytest.raises(ValidationError):
            CookStartRequest(sentence="ab")
        with pytest.raises(ValidationError):
            CookStartRequest(sentence="   x   ")

    def test_revise_note_required(self) -> None:
        assert CookReviseRequest(note="less spicy").note == "less spicy"
        with pytest.raises(ValidationError):
            CookReviseRequest(note="   ")
        with pytest.raises(ValidationError):
            ResumePayload(decision="revise")

    def test_confirm_etag_length(self) -> None:
        CookConfirmRequest(proposal_etag="a" * 64)
        with pytest.raises(ValidationError):
            CookConfirmRequest(proposal_etag="short")
