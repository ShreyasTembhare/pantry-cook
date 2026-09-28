"""A checkpoint written by one graph can be resumed by another."""

import sqlite3
from decimal import Decimal

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Item, Meal
from app.db.repositories import ItemRepository
from app.domain.units import Unit
from app.graph.builder import build_graph
from app.graph.checkpointer import StreamingSqliteSaver
from app.graph.llm import FakeMealModel
from app.graph.state import initial_cook_state
from app.schemas.items import ItemCreate
from tests.support import soon


def test_resume_after_graph_rebuild(
    session_factory: sessionmaker[Session], tmp_path: object
) -> None:
    db = session_factory()
    leeks = ItemRepository(db).create(
        ItemCreate(name="Leeks", quantity=Decimal("300"), unit=Unit.G, expires_on=soon(1))
    )
    ItemRepository(db).create(
        ItemCreate(name="Eggs", quantity=Decimal("6"), unit=Unit.COUNT, expires_on=soon(4))
    )
    db.commit()
    leeks_id = leeks.id
    db.close()

    checkpoint = tmp_path / "checkpoints.sqlite"  # type: ignore[operator]
    thread_id = "restart-me"
    config = {"configurable": {"thread_id": thread_id}}

    conn = sqlite3.connect(str(checkpoint), check_same_thread=False)
    saver = SqliteSaver(conn)
    saver.setup()
    graph = build_graph(saver, FakeMealModel(), session_factory)
    graph.invoke(
        initial_cook_state(thread_id, "something warm with the leeks"),
        config,
        durability="sync",
    )
    paused = graph.get_state(config)
    assert paused.next == ("await_user",)
    conn.commit()
    conn.close()
    del graph

    conn2 = sqlite3.connect(str(checkpoint), check_same_thread=False)
    saver2 = SqliteSaver(conn2)
    saver2.setup()
    rebuilt = build_graph(saver2, FakeMealModel(), session_factory)
    rebuilt.invoke(Command(resume={"decision": "confirm"}), config, durability="sync")

    db = session_factory()
    leeks = db.get(Item, leeks_id)
    assert leeks is not None
    assert Decimal(str(leeks.quantity_base)) == Decimal("150")
    meals = db.execute(select(Meal)).scalars().all()
    assert len(meals) == 1
    assert meals[0].status == "cooked"
    db.close()
    conn2.close()


async def test_astream_then_sync_resume(
    session_factory: sessionmaker[Session], tmp_path: object
) -> None:
    """The file checkpointer must serve astream and a later sync resume."""
    db = session_factory()
    ItemRepository(db).create(
        ItemCreate(name="Leeks", quantity=Decimal("300"), unit=Unit.G, expires_on=soon(1))
    )
    db.commit()
    db.close()

    checkpoint = tmp_path / "stream.sqlite"  # type: ignore[operator]
    thread_id = "stream-then-resume"
    config = {"configurable": {"thread_id": thread_id}}
    conn = sqlite3.connect(str(checkpoint), check_same_thread=False, timeout=30)
    saver = StreamingSqliteSaver(conn)
    saver.setup()
    graph = build_graph(saver, FakeMealModel(), session_factory)
    nodes: list[str] = []
    async for mode, data in graph.astream(
        initial_cook_state(thread_id, "something warm with the leeks"),
        config,
        stream_mode=["updates", "messages"],
        durability="sync",
    ):
        if mode == "updates" and isinstance(data, dict):
            nodes.extend(name for name in data if not str(name).startswith("__"))
    assert "propose_meal" in nodes
    paused = graph.get_state(config)
    assert paused.next == ("await_user",)

    graph.invoke(Command(resume={"decision": "abandon"}), config, durability="sync")
    finished = graph.get_state(config)
    assert finished.next == ()
    assert finished.values["decision"] == "abandon"
    conn.close()
