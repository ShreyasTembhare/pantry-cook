"""Chat HTTP: add, cook, and a delete that does not land until confirm."""

from collections.abc import Generator
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import MemorySaver
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_chat_model, get_db, get_graph
from app.graph.builder import build_graph
from app.graph.llm import FakeMealModel
from app.main import create_app


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
        yield SimpleNamespace(client=client)


def _say(client: TestClient, text: str) -> dict[str, object]:
    response = client.post("/api/chat/messages", json={"text": text})
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, dict)
    return body


class TestChatApi:
    def test_add_item_shows_up_in_the_pantry(self, chat: SimpleNamespace) -> None:
        body = _say(chat.client, "2 leeks and 500 g chicken")
        assistant = body["assistant"]
        assert isinstance(assistant, dict)
        cards = assistant["cards"]
        assert isinstance(cards, list)
        assert cards[0]["type"] == "pantry"
        listed = chat.client.get("/api/items")
        assert listed.status_code == 200
        names = {row["name"] for row in listed.json()}
        assert names == {"Leeks", "Chicken"}

    def test_start_cook_returns_a_proposal(self, chat: SimpleNamespace) -> None:
        _say(chat.client, "2 leeks")
        body = _say(chat.client, "something warm with the leeks")
        assistant = body["assistant"]
        assert isinstance(assistant, dict)
        card = assistant["cards"][0]
        assert card["type"] == "proposal"
        assert card["proposal"]["title"]
        assert card["proposal_etag"]

    def test_delete_does_not_remove_until_confirm(self, chat: SimpleNamespace) -> None:
        _say(chat.client, "2 leeks")
        asked = _say(chat.client, "remove the leeks")
        assistant = asked["assistant"]
        assert isinstance(assistant, dict)
        card = assistant["cards"][0]
        assert card["type"] == "pending"
        assert card["pending_kind"] == "delete_item"
        still = chat.client.get("/api/items")
        assert len(still.json()) == 1

        confirmed = chat.client.post(f"/api/chat/pending/{card['pending_id']}/confirm")
        assert confirmed.status_code == 200, confirmed.text
        assert chat.client.get("/api/items").json() == []

        history = chat.client.get("/api/chat")
        assert history.status_code == 200
        assert len(history.json()["messages"]) >= 3
