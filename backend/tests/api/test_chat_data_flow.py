"""Every chat tool against the real tables: cards, API reads, and stored rows must agree."""

from collections.abc import Generator
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import MemorySaver
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_chat_model, get_db, get_graph
from app.graph.builder import build_graph
from app.graph.llm import FakeMealModel
from app.main import create_app
from app.schemas.chat import DraftChatAction, DraftChatPlan
from app.schemas.llm import MealProposal, ProposedMissingLine, ProposedUseLine


@pytest.fixture
def chat(session_factory: sessionmaker[Session]) -> Generator[SimpleNamespace, None, None]:
    llm = FakeMealModel()
    graph = build_graph(MemorySaver(), llm, session_factory)

    def override_db() -> Generator[Session, None, None]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_graph] = lambda: graph
    app.dependency_overrides[get_chat_model] = lambda: llm
    with TestClient(app) as client:
        yield SimpleNamespace(client=client, llm=llm)


def _say(client: TestClient, text: str) -> dict[str, Any]:
    response = client.post("/api/chat/messages", json={"text": text})
    assert response.status_code == 200, response.text
    return response.json()["assistant"]


def _items(client: TestClient) -> dict[str, dict[str, Any]]:
    rows = client.get("/api/items").json()
    return {row["name"]: row for row in rows}


def _add(
    client: TestClient, name: str, quantity: str, unit: str, **extra: object
) -> dict[str, Any]:
    response = client.post(
        "/api/items", json={"name": name, "quantity": quantity, "unit": unit, **extra}
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_cook_undo_and_shopping_list_keep_cards_and_rows_in_step(chat: SimpleNamespace) -> None:
    client = chat.client
    soon = (date.today() + timedelta(days=2)).isoformat()
    chicken = _add(client, "Chicken", "500", "g", expires_on=soon)
    leeks = _add(client, "Leeks", "2", "count")
    chat.llm.script.append(
        MealProposal(
            title="Chicken and leeks",
            servings=2,
            lines=[
                ProposedUseLine(item_id=chicken["id"], quantity=Decimal("300"), unit="g"),
                ProposedUseLine(item_id=leeks["id"], quantity=Decimal("1"), unit="count"),
                ProposedMissingLine(name="cream", quantity_note="a splash"),
            ],
            steps=["Brown the chicken.", "Add the leeks."],
        )
    )

    proposal = _say(client, "use the chicken before it goes off")
    card = proposal["cards"][0]
    assert card["type"] == "proposal"
    assert card["proposal"]["title"] == "Chicken and leeks"
    used = {line["item_id"] for line in card["proposal"]["lines"] if line["kind"] == "use"}
    assert used == {chicken["id"], leeks["id"]}
    assert Decimal(_items(client)["Chicken"]["quantity"]) == Decimal("500")
    assert client.get("/api/chat").json()["active_cook_session_id"] == card["cook_session_id"]

    asked = _say(client, "looks good")["cards"][0]
    assert asked["pending_kind"] == "confirm_cook"
    assert asked["proposal_etag"] == card["proposal_etag"]
    assert Decimal(_items(client)["Chicken"]["quantity"]) == Decimal("500")

    cooked = _say(client, "yes")
    assert cooked["content"] == "Cooked Chicken and leeks."
    meal_card = cooked["cards"][0]
    assert meal_card["type"] == "meal"
    assert Decimal(_items(client)["Chicken"]["quantity"]) == Decimal("200")
    assert Decimal(_items(client)["Leeks"]["quantity"]) == Decimal("1")
    assert client.get("/api/chat").json()["active_cook_session_id"] is None
    meals = client.get("/api/meals").json()
    assert [(meal["id"], meal["status"]) for meal in meals] == [(meal_card["meal"]["id"], "cooked")]

    listed = _say(client, "what did I cook")["cards"][0]
    assert [meal["title"] for meal in listed["meals"]] == ["Chicken and leeks"]

    unsized = _say(client, "bought the cream")["cards"][0]
    assert unsized["type"] == "error"
    assert unsized["error"]["code"] == "quantity_required"
    assert "Cream" not in _items(client)

    bought = _say(client, "bought 200 ml cream")["cards"][0]
    assert bought["type"] == "meal"
    assert sorted(_items(client)) == ["Chicken", "Cream", "Leeks"], bought["title"]
    cream = _items(client)["Cream"]
    assert (Decimal(cream["quantity"]), cream["unit"]) == (Decimal("200"), "ml")

    undo = _say(client, "undo that")["cards"][0]
    assert undo["pending_kind"] == "undo_meal"
    assert undo["meal"]["id"] == meal_card["meal"]["id"]
    assert client.get("/api/meals").json()[0]["status"] == "cooked"
    _say(client, "yes")
    restored = _items(client)
    assert Decimal(restored["Chicken"]["quantity"]) == Decimal("500")
    assert Decimal(restored["Leeks"]["quantity"]) == Decimal("2")
    assert client.get("/api/meals").json() == []
    assert client.get("/api/meals", params={"status": "undone"}).json()[0]["status"] == "undone"
    assert _say(client, "what did I cook")["cards"][0]["title"] == "No cooked meals yet."


def test_update_list_and_delete_agree_with_the_items_api(chat: SimpleNamespace) -> None:
    client = chat.client
    _add(client, "Rice", "1", "kg", expires_on="2026-01-01")

    listed = _say(client, "what's in the pantry")["cards"][0]
    assert [row["name"] for row in listed["items"]] == ["Rice"]
    assert listed["items"][0]["expires_on"] == "2026-01-01"

    updated = _say(client, "set the rice to 3 kg")["cards"][0]
    assert updated["items"][0]["quantity"] in {"3", "3.00", "3.0"}
    assert Decimal(_items(client)["Rice"]["quantity"]) == Decimal("3")

    asked = _say(client, "remove the rice")["cards"][0]
    assert asked["items"][0]["name"] == "Rice"
    assert "Rice" in _items(client)
    _say(client, "no")
    assert "Rice" in _items(client)
    _say(client, "remove the rice")
    _say(client, "yeah")
    assert _items(client) == {}


def test_model_answers_use_the_live_pantry(chat: SimpleNamespace) -> None:
    client = chat.client
    _add(client, "Spinach", "100", "g", expires_on="2026-01-01")
    chat.llm.script.append(
        DraftChatPlan(
            reply="The spinach is past its date.",
            actions=[DraftChatAction(tool="list_pantry")],
        )
    )
    reply = _say(client, "kal shda")
    assert reply["content"] == "The spinach is past its date."
    assert reply["cards"][0]["items"][0]["name"] == "Spinach"
    sent = chat.llm.received[-1][1].content
    assert '"expired": true' in sent
    assert '"quantity": "100"' in sent


def test_cook_request_on_an_empty_pantry_is_a_clear_error_card(chat: SimpleNamespace) -> None:
    card = _say(chat.client, "use the chicken before it goes off")["cards"][0]
    assert card["type"] == "error"
    assert card["error"]["code"] == "empty_pantry"
