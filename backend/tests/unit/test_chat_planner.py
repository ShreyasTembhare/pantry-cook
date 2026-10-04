"""Hybrid planner: rules first, scripted model second, never a write on a doubtful plan."""

from collections.abc import Generator
from datetime import date, timedelta
from decimal import Decimal

import pytest
from langgraph.checkpoint.memory import MemorySaver
from sqlalchemy.orm import Session, sessionmaker

from app.db.repositories import ChatRepository, ItemRepository
from app.domain.chat import MODEL_UNAVAILABLE_REPLY, _answer, rules_chat_plan, run_turn
from app.domain.chat_planner import (
    build_context,
    checked_plan,
    model_plan,
    wants_model,
)
from app.graph.builder import build_graph
from app.graph.llm import FakeMealModel
from app.schemas.chat import ChatAction, ChatPlan, DraftChatAction, DraftChatPlan


@pytest.fixture
def chef(
    session_factory: sessionmaker[Session],
) -> Generator[tuple[Session, object, FakeMealModel], None, None]:
    db = session_factory()
    llm = FakeMealModel()
    graph = build_graph(MemorySaver(), llm, session_factory)
    try:
        yield db, graph, llm
    finally:
        db.close()


def _draft(reply: str, **action: object) -> DraftChatPlan:
    actions = [DraftChatAction.model_validate(action)] if action else []
    return DraftChatPlan(reply=reply, actions=actions)


def test_expiring_phrases_start_a_cook_without_the_model() -> None:
    plan = rules_chat_plan("use the chicken before it goes off")
    assert plan.actions[0].tool == "start_cook"
    plan = rules_chat_plan("use the spinach, it is about to expire")
    assert plan.actions[0].tool == "start_cook"
    # Questions about what is expiring are for the planner, not a cook request.
    assert rules_chat_plan("what should I use up first?").actions == []
    assert rules_chat_plan("what is expiring soon").actions == []


def test_answers_ignore_case_punctuation_and_please() -> None:
    assert _answer("Yes!") == "yes"
    assert _answer("yeah, please") == "yes"
    assert _answer("Nope.") == "no"
    assert _answer("yes, and add rice") is None


def test_wants_model_only_for_real_or_scripted_plans() -> None:
    fake = FakeMealModel()
    assert wants_model(fake) is False
    fake.script.append(_draft("hi"))
    assert wants_model(fake) is True


def test_draft_plan_converts_floats_and_units() -> None:
    plan = _draft("Set.", tool="update_item", item_name="rice", quantity=2.5, unit="kg").to_plan()
    action = plan.actions[0]
    assert action.quantity == Decimal("2.5")
    assert action.unit is not None
    assert action.unit.value == "kg"


def test_rules_win_and_the_model_is_never_asked(
    chef: tuple[Session, object, FakeMealModel],
) -> None:
    db, graph, llm = chef
    llm.script.append(_draft("should not be used", tool="list_pantry"))
    run_turn(db, graph, llm, "2 leeks")
    assert len(llm.script) == 1
    assert llm.received == []


def test_model_answers_when_rules_find_nothing(
    chef: tuple[Session, object, FakeMealModel],
) -> None:
    db, graph, llm = chef
    run_turn(db, graph, llm, "2 leeks")
    llm.script.append(_draft("Nothing in the pantry expires soon."))
    turn = run_turn(db, graph, llm, "kal shda")
    assert turn.assistant.content == "Nothing in the pantry expires soon."
    assert turn.assistant.cards == []
    context = llm.received[-1][1].content
    assert "Leeks" in context
    assert "kal shda" in context


def test_model_context_carries_quantity_expiry_and_history(
    chef: tuple[Session, object, FakeMealModel],
) -> None:
    db, graph, llm = chef
    past = (date.today() - timedelta(days=2)).isoformat()
    run_turn(db, graph, llm, "500 g chicken")
    item = ItemRepository(db).list()[0]
    item.expires_on = date.fromisoformat(past)
    db.commit()
    thread = ChatRepository(db).home_thread()
    context = build_context(db, thread, None)
    row = context["pantry"][0]
    assert row["name"] == "Chicken"
    assert row["quantity"] == "500"
    assert row["unit"] == "g"
    assert row["expires_on"] == past
    assert row["expired"] is True
    # The newest message is the one being planned, so history stops before it.
    assert len(context["recent_messages"]) == 1
    assert context["pending"] is None
    assert context["active_cook"] == {"present": False}


def test_model_add_goes_through_the_normal_write_path(
    chef: tuple[Session, object, FakeMealModel],
) -> None:
    db, graph, llm = chef
    llm.script.append(_draft("Adding.", tool="add_items", sentence="3 eggs"))
    turn = run_turn(db, graph, llm, "put eggs in please")
    assert turn.assistant.cards[0].type == "pantry"
    assert [item.name for item in ItemRepository(db).list()] == ["Eggs"]


def test_model_delete_still_waits_for_confirmation(
    chef: tuple[Session, object, FakeMealModel],
) -> None:
    db, graph, llm = chef
    run_turn(db, graph, llm, "2 leeks")
    llm.script.append(_draft("Remove them?", tool="delete_item", item_name="leeks"))
    turn = run_turn(db, graph, llm, "bin the green stuff")
    assert turn.assistant.cards[0].type == "pending"
    assert len(ItemRepository(db).list()) == 1


def test_model_failure_falls_back_with_no_write(
    chef: tuple[Session, object, FakeMealModel],
) -> None:
    db, graph, llm = chef
    run_turn(db, graph, llm, "2 leeks")
    llm.script.append(RuntimeError("boom"))
    turn = run_turn(db, graph, llm, "blah blah")
    assert turn.assistant.content == MODEL_UNAVAILABLE_REPLY
    assert turn.assistant.cards == []
    assert len(ItemRepository(db).list()) == 1


def test_model_timeout_falls_back(
    chef: tuple[Session, object, FakeMealModel], monkeypatch: pytest.MonkeyPatch
) -> None:
    import time

    from app.config import settings

    db, _graph, llm = chef
    monkeypatch.setattr(settings, "chat_planner_timeout", 0.05)

    def slow(self: FakeMealModel, schema: object) -> object:
        class Slow:
            def invoke(self, messages: object) -> object:
                time.sleep(0.5)
                return _draft("late")

        return Slow()

    monkeypatch.setattr(FakeMealModel, "with_structured_output", slow)
    llm.script.append(_draft("late"))
    thread = ChatRepository(db).home_thread()
    assert model_plan(llm, "hello", build_context(db, thread, None)) is None


def test_invalid_model_output_is_ignored(chef: tuple[Session, object, FakeMealModel]) -> None:
    db, _graph, llm = chef
    thread = ChatRepository(db).home_thread()
    context = build_context(db, thread, None)
    llm.script.append(_draft("Delete it.", tool="delete_item"))
    assert model_plan(llm, "remove it", context) is None


def test_checked_plan_rules() -> None:
    bare = {"active_cook_session_id": None}
    cooking = {"active_cook_session_id": "abc"}
    revise = ChatPlan(reply="Ok.", actions=[ChatAction(tool="revise_cook")])
    blocked = checked_plan(revise, "less salt", bare)
    assert blocked is not None
    assert blocked.actions == []
    kept = checked_plan(revise, "less salt", cooking)
    assert kept is not None
    assert kept.actions[0].note == "less salt"

    cook = checked_plan(
        ChatPlan(reply="Ok.", actions=[ChatAction(tool="start_cook")]), "use the eggs", bare
    )
    assert cook is not None
    assert cook.actions[0].sentence == "use the eggs"

    two = ChatPlan(
        reply="Ok.",
        actions=[ChatAction(tool="list_pantry"), ChatAction(tool="list_meals")],
    )
    only = checked_plan(two, "x", bare)
    assert only is not None
    assert [a.tool for a in only.actions] == ["list_pantry"]

    for bad in (
        ChatAction(tool="add_items"),
        ChatAction(tool="buy_missing"),
        ChatAction(tool="update_item", item_name="rice"),
        ChatAction(tool="update_item", item_name="rice", quantity=Decimal("0")),
    ):
        assert checked_plan(ChatPlan(reply="Ok.", actions=[bad]), "x", bare) is None


def test_open_confirmation_blocks_other_writes(
    chef: tuple[Session, object, FakeMealModel],
) -> None:
    db, graph, llm = chef
    run_turn(db, graph, llm, "2 leeks")
    run_turn(db, graph, llm, "remove the leeks")
    blocked = run_turn(db, graph, llm, "change the leeks to 5")
    assert "yes or no" in blocked.assistant.content
    assert blocked.assistant.cards == []
    items = ItemRepository(db).list()
    assert len(items) == 1
    assert items[0].quantity_base == Decimal("2")

    read_only = run_turn(db, graph, llm, "what's in the pantry")
    assert read_only.assistant.cards[0].type == "pantry"

    done = run_turn(db, graph, llm, "Yes, please.")
    assert done.assistant.cards[0].title.startswith("Removed")
    assert ItemRepository(db).list() == []


def test_new_cook_request_supersedes_a_stale_cook_confirmation(
    chef: tuple[Session, object, FakeMealModel],
) -> None:
    db, graph, llm = chef
    run_turn(db, graph, llm, "2 leeks")
    run_turn(db, graph, llm, "something warm with the leeks")
    asked = run_turn(db, graph, llm, "looks good")
    assert asked.assistant.cards[0].pending_kind == "confirm_cook"
    revised = run_turn(db, graph, llm, "fewer steps")
    assert revised.assistant.cards[0].type == "proposal"
    thread = ChatRepository(db).home_thread()
    stale = ChatRepository(db).open_pending(thread.id)
    assert stale is None
