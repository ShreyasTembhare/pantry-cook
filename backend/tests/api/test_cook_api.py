"""Non-streaming cook API: start, revise, confirm, abandon, stale proposals."""

from collections.abc import Generator
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import MemorySaver
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_db, get_graph
from app.db.models import Base
from app.graph.builder import build_graph
from app.graph.llm import FakeMealModel
from app.main import create_app
from app.schemas.llm import MealProposal, ProposedMissingLine, ProposedUseLine


@pytest.fixture
def cook() -> Generator[SimpleNamespace, None, None]:
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=True) as handle:
        engine = create_engine(f"sqlite:///{handle.name}")

        def set_pragmas(dbapi_conn: object, _rec: object) -> None:
            cursor = dbapi_conn.cursor()  # type: ignore[union-attr]
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        event.listen(engine, "connect", set_pragmas)
        Base.metadata.create_all(bind=engine)
        factory = sessionmaker(bind=engine, expire_on_commit=False)

        def override_db() -> Generator[Session, None, None]:
            session = factory()
            try:
                yield session
            finally:
                session.close()

        llm = FakeMealModel()
        graph = build_graph(MemorySaver(), llm, factory)
        app = create_app()
        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_graph] = lambda: graph

        with TestClient(app) as client:
            yield SimpleNamespace(client=client, llm=llm, factory=factory)


def _add(
    client: TestClient, name: str, quantity: str, unit: str, **extra: object
) -> dict[str, object]:
    body: dict[str, object] = {"name": name, "quantity": quantity, "unit": unit, **extra}
    response = client.post("/api/items", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def _start(
    client: TestClient, sentence: str = "something warm with the leeks"
) -> dict[str, object]:
    response = client.post("/api/cook/start", json={"sentence": sentence})
    assert response.status_code == 201, response.text
    return response.json()


class TestCookApi:
    def test_start_returns_a_proposal(self, cook: SimpleNamespace) -> None:
        _add(cook.client, "Leeks", "300", "g", expires_on="2026-12-01")
        _add(cook.client, "Eggs", "6", "count")
        body = _start(cook.client)
        assert body["status"] == "awaiting_user"
        assert body["proposal"]["title"]
        assert body["proposal_etag"]
        assert len(str(body["proposal_etag"])) == 64
        assert body["attempt_count"] == 1

    def test_empty_pantry(self, cook: SimpleNamespace) -> None:
        response = cook.client.post("/api/cook/start", json={"sentence": "something warm"})
        assert response.status_code == 409
        assert response.headers["content-type"].startswith("application/problem+json")
        assert response.json()["code"] == "empty_pantry"
        assert response.headers["x-request-id"]

    def test_sentence_too_short(self, cook: SimpleNamespace) -> None:
        response = cook.client.post("/api/cook/start", json={"sentence": "ab"})
        assert response.status_code == 422
        assert response.json()["code"] == "validation_failed"

    def test_duplicate_names_still_rejected(self, cook: SimpleNamespace) -> None:
        _add(cook.client, "Rice", "500", "g")
        response = cook.client.post(
            "/api/items", json={"name": "rice", "quantity": "100", "unit": "g"}
        )
        assert response.status_code == 409
        assert response.json()["code"] == "duplicate_item"

    def test_ambiguous_sentence_explains_the_choice(self, cook: SimpleNamespace) -> None:
        _add(cook.client, "Spinach", "200", "g", expires_on="2026-10-01")
        body = _start(cook.client, "food")
        assert "open-ended" in str(body["proposal"]["rationale"])

    def test_zero_quantity_item_is_not_used(self, cook: SimpleNamespace) -> None:
        salt = _add(cook.client, "Salt", "0", "g")
        rice = _add(cook.client, "Rice", "500", "g")
        body = _start(cook.client, "a rice supper")
        use_ids = [line["item_id"] for line in body["proposal"]["lines"] if line["kind"] == "use"]
        assert rice["id"] in use_ids
        assert salt["id"] not in use_ids

    def test_revise_confirm_abandon_and_meals(self, cook: SimpleNamespace) -> None:
        leeks = _add(cook.client, "Leeks", "300", "g")
        started = _start(cook.client)
        thread_id = started["id"]

        revised = cook.client.post(
            f"/api/cook/{thread_id}/revise",
            json={"note": "fewer steps"},
        )
        assert revised.status_code == 200, revised.text
        revised_body = revised.json()
        assert revised_body["status"] == "awaiting_user"
        assert revised_body["attempt_count"] >= 2
        assert revised_body["proposal"]["steps"] == ["Cook everything in one pan and serve."]

        confirmed = cook.client.post(
            f"/api/cook/{thread_id}/confirm",
            json={"proposal_etag": revised_body["proposal_etag"]},
        )
        assert confirmed.status_code == 200, confirmed.text
        meal = confirmed.json()
        assert meal["status"] == "cooked"
        assert meal["title"]
        assert any(line["kind"] == "missing" for line in meal["lines"])

        listed = cook.client.get("/api/meals")
        assert listed.status_code == 200
        assert len(listed.json()) == 1
        detail = cook.client.get(f"/api/meals/{meal['id']}")
        assert detail.status_code == 200
        assert detail.json()["sentence"] == "something warm with the leeks"

        again = cook.client.post(
            f"/api/cook/{thread_id}/confirm",
            json={"proposal_etag": revised_body["proposal_etag"]},
        )
        assert again.status_code == 409
        assert again.json()["code"] == "session_not_awaiting"

        leeks_now = cook.client.get(f"/api/items/{leeks['id']}")
        assert Decimal(leeks_now.json()["quantity"]) == Decimal("150")

    def test_abandon_is_idempotent(self, cook: SimpleNamespace) -> None:
        _add(cook.client, "Leeks", "300", "g")
        started = _start(cook.client)
        thread_id = started["id"]
        first = cook.client.post(f"/api/cook/{thread_id}/abandon")
        assert first.status_code == 200
        assert first.json()["status"] == "abandoned"
        second = cook.client.post(f"/api/cook/{thread_id}/abandon")
        assert second.status_code == 200
        assert second.json()["status"] == "abandoned"
        confirm = cook.client.post(
            f"/api/cook/{thread_id}/confirm",
            json={"proposal_etag": started["proposal_etag"]},
        )
        assert confirm.status_code == 409
        assert confirm.json()["code"] == "session_not_awaiting"

    def test_etag_mismatch_stays_awaiting(self, cook: SimpleNamespace) -> None:
        _add(cook.client, "Leeks", "300", "g")
        started = _start(cook.client)
        thread_id = started["id"]
        response = cook.client.post(
            f"/api/cook/{thread_id}/confirm",
            json={"proposal_etag": "a" * 64},
        )
        assert response.status_code == 409
        body = response.json()
        assert body["code"] == "stale_proposal"
        assert body["extra"]["reason"] == "proposal_etag_mismatch"
        current = cook.client.get(f"/api/cook/{thread_id}")
        assert current.json()["status"] == "awaiting_user"

    def test_stale_proposal_reports_changed_items(self, cook: SimpleNamespace) -> None:
        leeks = _add(cook.client, "Leeks", "300", "g")
        started = _start(cook.client)
        thread_id = started["id"]
        patched = cook.client.patch(
            f"/api/items/{leeks['id']}",
            json={"quantity": "100", "version": leeks["version"]},
        )
        assert patched.status_code == 200
        response = cook.client.post(
            f"/api/cook/{thread_id}/confirm",
            json={"proposal_etag": started["proposal_etag"]},
        )
        assert response.status_code == 409
        body = response.json()
        assert body["code"] == "stale_proposal"
        assert leeks["id"] in body["extra"]["changed_item_ids"]
        current = cook.client.get(f"/api/items/{leeks['id']}")
        assert Decimal(current.json()["quantity"]) == Decimal("100")
        assert cook.client.get("/api/meals").json() == []

    def test_revision_history_keeps_the_note_and_both_proposals(
        self, cook: SimpleNamespace
    ) -> None:
        _add(cook.client, "Leeks", "300", "g")
        started = _start(cook.client)
        assert [item["attempt_no"] for item in started["attempts"]] == [1]
        assert started["attempts"][0]["trigger"] == "initial"
        assert started["attempts"][0]["user_note"] is None
        first_title = started["attempts"][0]["proposal"]["title"]

        revised = cook.client.post(
            f"/api/cook/{started['id']}/revise",
            json={"note": "fewer steps"},
        )
        assert revised.status_code == 200, revised.text
        attempts = revised.json()["attempts"]
        assert [item["attempt_no"] for item in attempts] == [1, 2]
        assert attempts[0]["trigger"] == "initial"
        assert attempts[0]["proposal"]["title"] == first_title
        assert attempts[0]["user_note"] is None
        assert attempts[1]["trigger"] == "user_revision"
        assert attempts[1]["user_note"] == "fewer steps"
        assert attempts[1]["proposal"]["title"]
        assert attempts[1]["proposal"]["steps"] == ["Cook everything in one pan and serve."]

        loaded = cook.client.get(f"/api/cook/{started['id']}")
        assert loaded.status_code == 200
        assert loaded.json()["attempts"][1]["user_note"] == "fewer steps"

    def test_reload_reads_the_checkpoint(self, cook: SimpleNamespace) -> None:
        _add(cook.client, "Leeks", "300", "g")
        started = _start(cook.client)
        loaded = cook.client.get(f"/api/cook/{started['id']}")
        assert loaded.status_code == 200
        assert loaded.json()["proposal"]["title"] == started["proposal"]["title"]
        assert loaded.json()["proposal_etag"] == started["proposal_etag"]

    def test_auto_repair_is_visible_on_the_session(self, cook: SimpleNamespace) -> None:
        leeks = _add(cook.client, "Leeks", "300", "g")
        cook.llm.script.append(
            MealProposal(
                title="Too much leek",
                servings=2,
                lines=[
                    ProposedUseLine(item_id=str(leeks["id"]), quantity=Decimal("9999"), unit="g")
                ],
                steps=["Eat."],
            )
        )
        body = _start(cook.client)
        assert body["attempt_count"] == 2
        assert body["status"] == "awaiting_user"
        assert [item["trigger"] for item in body["attempts"]] == ["initial", "auto_repair"]
        assert body["attempts"][0]["proposal"]["title"] == "Too much leek"
        assert body["attempts"][0]["user_note"] is None
        assert body["attempts"][1]["proposal"]["title"]

    def test_could_not_satisfy(self, cook: SimpleNamespace) -> None:
        leeks = _add(cook.client, "Leeks", "300", "g")
        bad = MealProposal(
            title="Too much leek",
            servings=2,
            lines=[ProposedUseLine(item_id=str(leeks["id"]), quantity=Decimal("9999"), unit="g")],
            steps=["Eat."],
        )
        cook.llm.script.extend([bad, bad, bad])
        response = cook.client.post(
            "/api/cook/start",
            json={"sentence": "something warm with the leeks"},
        )
        assert response.status_code == 422
        assert response.json()["code"] == "could_not_satisfy"

    def test_fully_consumed_item_stays_at_zero(self, cook: SimpleNamespace) -> None:
        rice = _add(cook.client, "Rice", "200", "g")
        cook.llm.script.append(
            MealProposal(
                title="Finish the rice",
                servings=2,
                lines=[
                    ProposedUseLine(item_id=str(rice["id"]), quantity=Decimal("200"), unit="g"),
                    ProposedMissingLine(name="olive oil", quantity_note="a splash"),
                ],
                steps=["Cook the rice."],
            )
        )
        started = _start(cook.client, "use the rice")
        confirmed = cook.client.post(
            f"/api/cook/{started['id']}/confirm",
            json={"proposal_etag": started["proposal_etag"]},
        )
        assert confirmed.status_code == 200, confirmed.text
        current = cook.client.get(f"/api/items/{rice['id']}")
        assert current.status_code == 200
        assert Decimal(current.json()["quantity"]) == Decimal("0")

    def test_expired_use_needs_an_acknowledgement(self, cook: SimpleNamespace) -> None:
        _add(cook.client, "Yoghurt", "400", "g", expires_on="2020-01-06")
        started = _start(cook.client, "something warm with the yoghurt")
        assert started["status"] == "awaiting_user"
        blocked = cook.client.post(
            f"/api/cook/{started['id']}/confirm",
            json={"proposal_etag": started["proposal_etag"]},
        )
        assert blocked.status_code == 409
        body = blocked.json()
        assert body["code"] == "expired_unacknowledged"
        assert body["extra"]["expired_items"][0]["name"] == "Yoghurt"
        still = cook.client.get("/api/items")
        assert Decimal(still.json()[0]["quantity"]) == Decimal("400")

        confirmed = cook.client.post(
            f"/api/cook/{started['id']}/confirm",
            json={"proposal_etag": started["proposal_etag"], "acknowledge_expired": True},
        )
        assert confirmed.status_code == 200, confirmed.text

    def test_timeout_and_rate_limit_are_problem_details(self, cook: SimpleNamespace) -> None:
        class RateLimitError(Exception):
            def __init__(self) -> None:
                super().__init__("busy")
                self.status_code = 429
                self.headers = {"retry-after": "8"}

        _add(cook.client, "Rice", "500", "g")
        cook.llm.script.append(TimeoutError("slow"))
        timed_out = cook.client.post(
            "/api/cook/start", json={"sentence": "something warm with the rice"}
        )
        assert timed_out.status_code == 504
        assert timed_out.json()["code"] == "llm_timeout"

        cook.llm.script.append(RateLimitError())
        limited = cook.client.post(
            "/api/cook/start", json={"sentence": "something warm with the rice"}
        )
        assert limited.status_code == 429
        assert limited.json()["code"] == "llm_rate_limited"
        assert limited.headers["retry-after"] == "8"

    def test_health_names_the_checkpointer_and_pending_cooks(self, cook: SimpleNamespace) -> None:
        health = cook.client.get("/api/health")
        assert health.status_code == 200
        body = health.json()
        assert body["db"] == "ok"
        assert body["checkpointer"] == "ok"
        assert body["llm"] == "fake"
        assert body["pending_sessions"] == 0
        assert body["status"] == "healthy"

    def test_missing_session_and_meal(self, cook: SimpleNamespace) -> None:
        missing = cook.client.get("/api/cook/does-not-exist")
        assert missing.status_code == 404
        assert missing.json()["code"] == "session_not_found"
        missing_meal = cook.client.get("/api/meals/does-not-exist")
        assert missing_meal.status_code == 404
        assert missing_meal.json()["code"] == "meal_not_found"
