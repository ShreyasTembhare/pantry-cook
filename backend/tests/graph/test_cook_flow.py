"""Cook graph flows with MemorySaver and the fake model."""

from decimal import Decimal

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Item, Meal
from app.db.repositories import ItemRepository
from app.domain.units import Unit
from app.graph.builder import build_graph
from app.graph.llm import FakeMealModel
from app.graph.state import initial_cook_state
from app.schemas.items import ItemCreate
from app.schemas.llm import MealProposal, ProposedUseLine
from tests.support import soon


def _seed(factory: sessionmaker[Session]) -> tuple[str, str]:
    db = factory()
    repo = ItemRepository(db)
    leeks = repo.create(
        ItemCreate(name="Leeks", quantity=Decimal("300"), unit=Unit.G, expires_on=soon(1))
    )
    eggs = repo.create(
        ItemCreate(name="Eggs", quantity=Decimal("6"), unit=Unit.COUNT, expires_on=soon(4))
    )
    db.commit()
    ids = (leeks.id, eggs.id)
    db.close()
    return ids


def _over(item_id: str) -> MealProposal:
    return MealProposal(
        title="Too much leek",
        servings=2,
        lines=[ProposedUseLine(item_id=item_id, quantity=Decimal("9999"), unit=Unit.G)],
        steps=["Eat."],
    )


def _run(graph: object, thread_id: str, sentence: str) -> dict[str, object]:
    config = {"configurable": {"thread_id": thread_id}}
    graph.invoke(  # type: ignore[attr-defined]
        initial_cook_state(thread_id, sentence),
        config,
        durability="sync",
    )
    return config


class TestCookFlow:
    def test_happy_path_confirms_and_subtracts(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        leeks_id, eggs_id = _seed(session_factory)
        graph = build_graph(MemorySaver(), FakeMealModel(), session_factory)
        config = _run(graph, "happy", "something warm with the leeks")
        paused = graph.get_state(config)
        assert paused.next == ("await_user",)
        assert paused.values["proposal"]["title"]
        assert paused.values["error"] is None

        graph.invoke(Command(resume={"decision": "confirm"}), config, durability="sync")
        finished = graph.get_state(config)
        assert finished.next == ()
        assert finished.values["result"]["meal_id"]
        assert finished.values["error"] is None

        db = session_factory()
        leeks = db.get(Item, leeks_id)
        eggs = db.get(Item, eggs_id)
        assert leeks is not None and eggs is not None
        assert Decimal(str(leeks.quantity_base)) == Decimal("150")
        assert Decimal(str(eggs.quantity_base)) == Decimal("3")
        assert len(db.execute(select(Meal)).scalars().all()) == 1
        db.close()

    def test_auto_repair_then_interrupt(self, session_factory: sessionmaker[Session]) -> None:
        leeks_id, _eggs_id = _seed(session_factory)
        llm = FakeMealModel(script=[_over(leeks_id)])
        graph = build_graph(MemorySaver(), llm, session_factory)
        config = _run(graph, "repair", "something warm with the leeks")
        paused = graph.get_state(config)
        assert paused.next == ("await_user",)
        assert len(paused.values["attempts"]) == 2
        assert paused.values["attempts"][0]["trigger"] == "initial"
        assert (
            paused.values["attempts"][0]["validation_errors"][0]["code"] == "insufficient_quantity"
        )
        assert paused.values["attempts"][1]["trigger"] == "auto_repair"
        assert paused.values["attempts"][1]["validation_errors"] == []

    def test_three_bad_proposals_fail_without_interrupt(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        leeks_id, _eggs_id = _seed(session_factory)
        llm = FakeMealModel(script=[_over(leeks_id), _over(leeks_id), _over(leeks_id)])
        graph = build_graph(MemorySaver(), llm, session_factory)
        config = _run(graph, "fail", "something warm with the leeks")
        finished = graph.get_state(config)
        assert finished.next == ()
        assert finished.values["error"]["code"] == "could_not_satisfy"
        db = session_factory()
        assert db.execute(select(Meal)).scalars().all() == []
        db.close()

    def test_revise_appends_the_note_and_a_new_attempt(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        _seed(session_factory)
        llm = FakeMealModel()
        graph = build_graph(MemorySaver(), llm, session_factory)
        config = _run(graph, "revise", "something warm with the leeks")
        graph.invoke(
            Command(resume={"decision": "revise", "note": "fewer steps"}),
            config,
            durability="sync",
        )
        paused = graph.get_state(config)
        assert paused.next == ("await_user",)
        assert paused.values["user_notes"] == ["fewer steps"]
        assert any(attempt["trigger"] == "user_revision" for attempt in paused.values["attempts"])
        assert "fewer steps" in str(llm.received)
        assert paused.values["proposal"]["steps"] == ["Cook everything in one pan and serve."]

    def test_abandon_does_not_commit(self, session_factory: sessionmaker[Session]) -> None:
        leeks_id, _eggs_id = _seed(session_factory)
        graph = build_graph(MemorySaver(), FakeMealModel(), session_factory)
        config = _run(graph, "abandon", "something warm with the leeks")
        graph.invoke(Command(resume={"decision": "abandon"}), config, durability="sync")
        finished = graph.get_state(config)
        assert finished.next == ()
        assert finished.values["decision"] == "abandon"
        assert finished.values["result"] is None
        db = session_factory()
        assert db.execute(select(Meal)).scalars().all() == []
        leeks = db.get(Item, leeks_id)
        assert leeks is not None
        assert Decimal(str(leeks.quantity_base)) == Decimal("300")
        db.close()

    def test_stale_pantry_is_recorded_and_not_subtracted(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        leeks_id, _eggs_id = _seed(session_factory)
        graph = build_graph(MemorySaver(), FakeMealModel(), session_factory)
        config = _run(graph, "stale", "something warm with the leeks")

        db = session_factory()
        leeks = db.get(Item, leeks_id)
        assert leeks is not None
        leeks.quantity_base = 80
        leeks.version = 5
        db.commit()
        db.close()

        graph.invoke(Command(resume={"decision": "confirm"}), config, durability="sync")
        finished = graph.get_state(config)
        assert finished.values["error"]["code"] == "stale_proposal"
        assert leeks_id in finished.values["error"]["changed_item_ids"]
        assert finished.values["result"] is None

        db = session_factory()
        leeks = db.get(Item, leeks_id)
        assert leeks is not None
        assert Decimal(str(leeks.quantity_base)) == Decimal("80")
        assert db.execute(select(Meal)).scalars().all() == []
        db.close()
