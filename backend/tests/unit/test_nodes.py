"""Each cook node, with the fake model where a model is involved."""

import time
from datetime import date, timedelta
from decimal import Decimal

import pytest
from langchain_core.runnables import RunnableLambda
from sqlalchemy.orm import Session, sessionmaker

from app.db.repositories import ItemRepository
from app.domain.units import Dimension, Unit
from app.graph.llm import FakeMealModel
from app.graph.nodes import (
    LlmCallError,
    _invoke_structured,
    commit_meal,
    find_violations,
    load_pantry,
    parse_sentence,
    propose_meal,
    rows_for_prompt,
    validate_proposal,
)
from app.graph.state import initial_cook_state
from app.schemas.items import ItemCreate
from app.schemas.llm import MealProposal, ProposedMissingLine
from tests.support import meal, pantry_row, soon, use_line


def _message_text(messages: object) -> str:
    return str(messages)


class TestLoadPantry:
    def test_orders_by_expiry_then_name(
        self, db_session: Session, session_factory: sessionmaker[Session]
    ) -> None:
        repo = ItemRepository(db_session)
        repo.create(ItemCreate(name="Rice", quantity=Decimal("500"), unit=Unit.G, expires_on=None))
        repo.create(
            ItemCreate(
                name="Milk",
                quantity=Decimal("1"),
                unit=Unit.L,
                expires_on=soon(1),
            )
        )
        repo.create(
            ItemCreate(
                name="Eggs",
                quantity=Decimal("6"),
                unit=Unit.COUNT,
                expires_on=soon(5),
            )
        )
        repo.create(
            ItemCreate(
                name="Apples",
                quantity=Decimal("4"),
                unit=Unit.COUNT,
                expires_on=soon(1),
            )
        )
        db_session.commit()

        state = load_pantry(initial_cook_state("s", "food"), session_factory)
        names = [row["name"] for row in state["pantry_snapshot"]]
        assert names == ["Apples", "Milk", "Eggs", "Rice"]

    def test_keeps_zero_quantity_rows(
        self, db_session: Session, session_factory: sessionmaker[Session]
    ) -> None:
        ItemRepository(db_session).create(
            ItemCreate(name="Salt", quantity=Decimal("0"), unit=Unit.G)
        )
        db_session.commit()
        state = load_pantry(initial_cook_state("s", "food"), session_factory)
        assert state["pantry_snapshot"][0]["name"] == "Salt"
        assert Decimal(state["pantry_snapshot"][0]["quantity_base"]) == Decimal("0")


class TestParseSentence:
    def test_ambiguous_sentence_is_nearly_empty(self) -> None:
        llm = FakeMealModel()
        state = initial_cook_state("s", "food")
        state["pantry_snapshot"] = [pantry_row("rice", "Rice", "500")]
        parsed = parse_sentence(state, llm)
        constraints = parsed["constraints"]
        assert constraints["must_use_item_ids"] == []
        assert constraints["dietary"] == []
        assert constraints["servings"] == 2
        assert constraints["free_text_notes"] == "ambiguous request"

    def test_maps_keywords_and_named_items(self) -> None:
        llm = FakeMealModel()
        state = initial_cook_state("s", "vegetarian warm leeks for 4 in 20 min")
        state["pantry_snapshot"] = [
            pantry_row("leeks", "Leeks", "300"),
            pantry_row("chicken", "Chicken", "400"),
        ]
        constraints = parse_sentence(state, llm)["constraints"]
        assert constraints["dietary"] == ["vegetarian"]
        assert constraints["mood"] == "warm"
        assert constraints["servings"] == 4
        assert constraints["max_minutes"] == 20
        assert constraints["must_use_item_ids"] == ["leeks"]


class TestProposeMeal:
    def test_prompt_includes_violations_and_notes(self) -> None:
        llm = FakeMealModel()
        state = initial_cook_state("s", "warm rice")
        state["pantry_snapshot"] = [pantry_row("rice", "Rice", "500")]
        state["constraints"] = {"servings": 2, "must_use_item_ids": ["rice"]}
        state["violations"] = [
            {
                "code": "insufficient_quantity",
                "message": "Wanted 800 but only 500 are available.",
                "item_id": "rice",
            }
        ]
        state["user_notes"] = ["less spicy"]
        propose_meal(state, llm)
        blob = _message_text(llm.received)
        assert "insufficient_quantity" in blob
        assert "less spicy" in blob
        assert "Rice" in blob

    def test_zero_quantity_is_hidden_unless_named(self) -> None:
        snapshot = [
            pantry_row("salt", "Salt", "0"),
            pantry_row("rice", "Rice", "500"),
        ]
        hidden = rows_for_prompt(snapshot, "a rice supper")
        assert [row["name"] for row in hidden] == ["Rice"]
        named = rows_for_prompt(snapshot, "use the salt")
        assert {row["name"] for row in named} == {"Salt", "Rice"}

    def test_a_timeout_is_not_retried_as_bad_json(self) -> None:
        llm = FakeMealModel(script=[TimeoutError("slow"), "unused"])
        state = initial_cook_state("s", "warm rice tonight")
        state["pantry_snapshot"] = [pantry_row("rice", "Rice", "500")]
        result = propose_meal(state, llm)
        assert result["proposal"] is None
        assert result["error"]["code"] == "llm_timeout"
        assert len(llm.received) == 1

    def test_a_rate_limit_keeps_retry_after(self) -> None:
        class RateLimitError(Exception):
            def __init__(self) -> None:
                super().__init__("busy")
                self.status_code = 429
                self.headers = {"retry-after": "12"}

        llm = FakeMealModel(script=[RateLimitError()])
        state = initial_cook_state("s", "warm rice tonight")
        result = propose_meal(state, llm)
        assert result["error"]["code"] == "llm_rate_limited"
        assert result["error"]["retry_after"] == 12
        assert len(llm.received) == 1

    def test_an_auth_error_is_unavailable(self) -> None:
        class AuthError(Exception):
            status_code = 401

        llm = FakeMealModel(script=[AuthError("bad key")])
        state = initial_cook_state("s", "warm rice tonight")
        result = parse_sentence(state, llm)
        assert result["error"]["code"] == "llm_unavailable"

    def test_invalid_output_is_still_retried(self) -> None:
        llm = FakeMealModel(script=["nope", "still nope", "nope again"])
        state = initial_cook_state("s", "warm rice tonight")
        result = propose_meal(state, llm)
        assert result["error"]["code"] == "llm_output_invalid"
        assert len(llm.received) == 3

    def test_the_node_wall_clock_stops_a_hung_call(self) -> None:
        class Sleepy:
            def with_structured_output(self, schema: object, **kwargs: object) -> RunnableLambda:
                del schema, kwargs

                def _call(messages: object) -> object:
                    del messages
                    time.sleep(0.3)
                    return None

                return RunnableLambda(_call)

        with pytest.raises(LlmCallError) as caught:
            _invoke_structured(Sleepy(), object, [], wall_seconds=0.05)  # type: ignore[arg-type]
        assert caught.value.code == "llm_timeout"


class TestValidateProposal:
    def test_valid_proposal_has_no_violations(self) -> None:
        proposal = meal(use_line("rice", "200"), title="Rice bowl")
        assert find_violations(proposal, [pantry_row("rice", "Rice", "500")]) == []

    @pytest.mark.parametrize(
        ("proposal", "snapshot", "code"),
        [
            (
                meal(use_line("missing", "10"), title="Mystery bowl"),
                [pantry_row("rice", "Rice", "500")],
                "unknown_item",
            ),
            (
                meal(use_line("flour", "200", Unit.ML), title="Wet flour"),
                [pantry_row("flour", "Flour", "500")],
                "dimension_mismatch",
            ),
            (
                meal(use_line("eggs", "1.5", Unit.COUNT), title="Eggy"),
                [
                    pantry_row(
                        "eggs",
                        "Eggs",
                        "6",
                        dimension=Dimension.COUNT,
                        unit=Unit.COUNT,
                    )
                ],
                "non_integer_count",
            ),
            (
                meal(use_line("rice", "800"), title="Too much rice"),
                [pantry_row("rice", "Rice", "500")],
                "insufficient_quantity",
            ),
            (
                meal(use_line("rice", "300"), use_line("rice", "300"), title="Double rice"),
                [pantry_row("rice", "Rice", "500")],
                "insufficient_quantity",
            ),
            (
                meal(use_line("salt", "1"), title="Salty"),
                [pantry_row("salt", "Salt", "0")],
                "insufficient_quantity",
            ),
            (
                MealProposal(
                    title="Just a list",
                    servings=2,
                    lines=[ProposedMissingLine(name="olive oil")],
                    steps=["Shop."],
                ),
                [pantry_row("rice", "Rice", "500")],
                "no_pantry_use",
            ),
        ],
    )
    def test_violation_codes(
        self,
        proposal: MealProposal,
        snapshot: list[dict[str, object]],
        code: str,
    ) -> None:
        found = find_violations(proposal, snapshot)  # type: ignore[arg-type]
        assert code in {item.code for item in found}

    def test_unknown_item_suggests_a_close_name(self) -> None:
        proposal = meal(use_line("tomatoes", "1"), title="Tomato toast")
        found = find_violations(proposal, [pantry_row("abc", "Tomatoes", "400")])
        assert found[0].code == "unknown_item"
        assert "abc" in found[0].message

    def test_unknown_item_without_a_match_asks_for_a_missing_line(self) -> None:
        proposal = meal(use_line("zzzz-not-food", "1"), title="Nonsense plate")
        found = find_violations(proposal, [pantry_row("rice", "Rice", "500")])
        assert "missing line" in found[0].message

    def test_expired_only_pantry_may_be_a_shopping_list(self) -> None:
        yesterday = date.today() - timedelta(days=1)
        proposal = MealProposal(
            title="Shopping-list supper",
            servings=2,
            lines=[ProposedMissingLine(name="olive oil")],
            steps=["Shop."],
        )
        snapshot = [pantry_row("yoghurt", "Yoghurt", "200", expires_on=yesterday)]
        assert find_violations(proposal, snapshot) == []

    def test_expiry_today_still_requires_a_use_line(self) -> None:
        proposal = MealProposal(
            title="Shopping-list supper",
            servings=2,
            lines=[ProposedMissingLine(name="olive oil")],
            steps=["Shop."],
        )
        snapshot = [pantry_row("spinach", "Spinach", "200", expires_on=date.today())]
        codes = {item.code for item in find_violations(proposal, snapshot)}
        assert "no_pantry_use" in codes

    def test_over_consumption_feeds_the_repair_budget(self) -> None:
        state = initial_cook_state("s", "rice")
        state["pantry_snapshot"] = [pantry_row("rice", "Rice", "100")]
        state["proposal"] = meal(use_line("rice", "500"), title="Too much rice").model_dump(
            mode="json"
        )
        updated = validate_proposal(state)
        assert updated["violations"][0]["code"] == "insufficient_quantity"
        assert updated["repair_used"] == 1
        assert updated["error"] is None
        assert updated["next_trigger"] == "auto_repair"
        assert "requested" in updated["violations"][0]["detail"]

    def test_third_failure_stops_with_could_not_satisfy(self) -> None:
        state = initial_cook_state("s", "rice")
        state["pantry_snapshot"] = [pantry_row("rice", "Rice", "100")]
        state["proposal"] = meal(use_line("rice", "500"), title="Too much rice").model_dump(
            mode="json"
        )
        state["repair_used"] = 2
        state["attempts"] = [{"attempt_no": 1}, {"attempt_no": 2}]
        updated = validate_proposal(state)
        assert updated["error"]["code"] == "could_not_satisfy"


class TestCommitNode:
    def test_records_result(
        self, db_session: Session, session_factory: sessionmaker[Session]
    ) -> None:
        rice = ItemRepository(db_session).create(
            ItemCreate(name="Rice", quantity=Decimal("500"), unit=Unit.G)
        )
        db_session.commit()
        state = initial_cook_state("session-node", "rice")
        state["pantry_snapshot"] = [pantry_row(rice.id, "Rice", "500", version=1)]
        state["proposal"] = meal(use_line(rice.id, "100"), title="Small rice").model_dump(
            mode="json"
        )
        result = commit_meal(state, session_factory)
        assert result["error"] is None
        assert result["result"]["title"] == "Small rice"
        db_session.expire_all()
        refreshed = db_session.get(type(rice), rice.id)
        assert refreshed is not None
        assert Decimal(str(refreshed.quantity_base)) == Decimal("400")

    def test_stale_proposal_is_an_error_and_does_not_subtract(
        self, db_session: Session, session_factory: sessionmaker[Session]
    ) -> None:
        rice = ItemRepository(db_session).create(
            ItemCreate(name="Rice", quantity=Decimal("500"), unit=Unit.G)
        )
        db_session.commit()
        rice.version = 3
        db_session.commit()
        state = initial_cook_state("session-stale", "rice")
        state["pantry_snapshot"] = [pantry_row(rice.id, "Rice", "500", version=1)]
        state["proposal"] = meal(use_line(rice.id, "100"), title="Stale rice").model_dump(
            mode="json"
        )
        result = commit_meal(state, session_factory)
        assert result["result"] is None
        assert result["error"]["code"] == "stale_proposal"
        assert rice.id in result["error"]["changed_item_ids"]
        db_session.expire_all()
        refreshed = db_session.get(type(rice), rice.id)
        assert refreshed is not None
        assert Decimal(str(refreshed.quantity_base)) == Decimal("500")
