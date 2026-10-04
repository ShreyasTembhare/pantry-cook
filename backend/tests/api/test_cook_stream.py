"""SSE cook stream: event order with the offline chef, no API key."""

import json
from collections.abc import Generator
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_db, get_graph
from app.config import settings
from app.graph.builder import build_graph
from app.graph.checkpointer import open_postgres_saver
from app.graph.llm import FakeMealModel
from app.main import create_app


@pytest.fixture
def cook(session_factory: sessionmaker[Session]) -> Generator[SimpleNamespace, None, None]:
    def override_db() -> Generator[Session, None, None]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    saver = open_postgres_saver(settings.database_url)
    graph = build_graph(saver, FakeMealModel(), session_factory)
    app = create_app()
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_graph] = lambda: graph

    try:
        with TestClient(app) as client:
            yield SimpleNamespace(client=client, factory=session_factory)
    finally:
        saver.conn.close()


def _parse_sse(raw: str) -> list[tuple[str, dict[str, object]]]:
    events: list[tuple[str, dict[str, object]]] = []
    name = "message"
    data: list[str] = []
    for line in raw.splitlines():
        if line.startswith("event:"):
            name = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            data.append(line.split(":", 1)[1].strip())
        elif line == "" and data:
            payload = json.loads("\n".join(data))
            assert isinstance(payload, dict)
            events.append((name, payload))
            name = "message"
            data = []
    return events


def _events(client: TestClient, thread_id: str) -> list[tuple[str, dict[str, object]]]:
    with client.stream("GET", f"/api/cook/{thread_id}/stream") as response:
        assert response.status_code == 200, response.read()
        assert response.headers["content-type"].startswith("text/event-stream")
        raw = "".join(response.iter_text())
    return _parse_sse(raw)


class TestCookStream:
    def test_event_order_with_the_fake_model(self, cook: SimpleNamespace) -> None:
        created = cook.client.post(
            "/api/items",
            json={"name": "Leeks", "quantity": "300", "unit": "g"},
        )
        assert created.status_code == 201, created.text
        started = cook.client.post(
            "/api/cook/start",
            json={"sentence": "something warm with the leeks", "defer": True},
        )
        assert started.status_code == 201, started.text
        body = started.json()
        assert body["status"] == "running"
        assert body["proposal"] is None

        events = _events(cook.client, body["id"])
        names = [name for name, _payload in events]
        assert "node_started" in names
        assert names.index("proposal") < names.index("awaiting_user") < names.index("done")
        assert names.index("node_started") < names.index("proposal")
        assert "proposal_token" in names
        assert names.index("proposal_token") < names.index("proposal")

        proposal = next(payload for name, payload in events if name == "proposal")
        assert proposal["title"]
        done = next(payload for name, payload in events if name == "done")
        assert done["status"] == "awaiting_user"
        session = done["session"]
        assert isinstance(session, dict)
        assert session["status"] == "awaiting_user"
        assert session["proposal_etag"]

        follow = cook.client.get(f"/api/cook/{body['id']}")
        assert follow.status_code == 200
        assert follow.json()["status"] == "awaiting_user"
        assert follow.json()["proposal"]["title"] == proposal["title"]

    def test_reconnect_replays_a_finished_proposal(self, cook: SimpleNamespace) -> None:
        cook.client.post("/api/items", json={"name": "Eggs", "quantity": "6", "unit": "count"})
        started = cook.client.post(
            "/api/cook/start",
            json={"sentence": "something warm with the eggs", "defer": True},
        )
        thread_id = started.json()["id"]
        first = _events(cook.client, thread_id)
        assert first[-1][0] == "done"

        second = _events(cook.client, thread_id)
        names = [name for name, _payload in second]
        assert "proposal" in names
        assert names[-2] == "awaiting_user"
        assert names[-1] == "done"
        assert second[-1][1]["status"] == "awaiting_user"
