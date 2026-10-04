"""Offline chat plans and the tool dispatch that sits behind them."""

from collections.abc import Generator

import pytest
from langgraph.checkpoint.memory import MemorySaver
from sqlalchemy.orm import Session, sessionmaker

from app.db.repositories import ItemRepository
from app.domain.chat import rules_chat_plan, run_turn
from app.graph.builder import build_graph
from app.graph.llm import FakeMealModel


def test_pantry_sentence_plans_an_add() -> None:
    plan = rules_chat_plan("2 leeks and 500 g chicken")
    assert plan.actions[0].tool == "add_items"
    assert plan.actions[0].sentence == "2 leeks and 500 g chicken"


def test_remove_plans_a_delete_not_a_write() -> None:
    plan = rules_chat_plan("remove the leeks")
    assert plan.actions[0].tool == "delete_item"
    assert plan.actions[0].item_name == "leeks"


def test_warm_sentence_starts_a_cook() -> None:
    plan = rules_chat_plan("something warm with the leeks")
    assert plan.actions[0].tool == "start_cook"


def test_tailor_words_revise_the_open_meal() -> None:
    plan = rules_chat_plan("fewer steps, and vegetarian")
    assert plan.actions[0].tool == "revise_cook"


def test_remaining_phrases_pick_a_tool() -> None:
    updated = rules_chat_plan("set the rice to 2 kg")
    assert updated.actions[0].tool == "update_item"
    assert updated.actions[0].unit is not None
    bare = rules_chat_plan("set the rice to 2")
    assert bare.actions[0].unit is None

    assert rules_chat_plan("what's in the pantry").actions[0].tool == "list_pantry"
    assert rules_chat_plan("undo that").actions[0].tool == "undo_meal"
    assert rules_chat_plan("what did I cook").actions[0].tool == "list_meals"
    assert rules_chat_plan("bought the chicken").actions[0].tool == "buy_missing"
    assert rules_chat_plan("abandon this meal").actions[0].tool == "abandon_cook"
    assert rules_chat_plan("looks good").actions[0].tool == "confirm_cook"
    revised = rules_chat_plan("revise the meal:")
    assert revised.actions[0].tool == "revise_cook"
    assert revised.actions[0].note
    cooking = rules_chat_plan("make it blue", {"active_cook_session_id": "session"})
    assert cooking.actions[0].tool == "revise_cook"
    assert rules_chat_plan("hello there").actions == []


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


def test_add_turn_writes_items(chef: tuple[Session, object, FakeMealModel]) -> None:
    db, graph, llm = chef
    turn = run_turn(db, graph, llm, "2 leeks and 500 g chicken")
    names = [item.name for item in ItemRepository(db).list(sort_by="name")]
    assert names == ["Chicken", "Leeks"]
    assert turn.assistant.cards[0].type == "pantry"
    assert "Added" in turn.assistant.cards[0].title


def test_delete_stays_pending_until_yes(chef: tuple[Session, object, FakeMealModel]) -> None:
    db, graph, llm = chef
    run_turn(db, graph, llm, "2 leeks")
    asked = run_turn(db, graph, llm, "remove the leeks")
    assert asked.assistant.cards[0].type == "pending"
    assert [item.name for item in ItemRepository(db).list()] == ["Leeks"]

    done = run_turn(db, graph, llm, "yes")
    assert done.assistant.cards[0].type == "pantry"
    assert ItemRepository(db).list() == []
