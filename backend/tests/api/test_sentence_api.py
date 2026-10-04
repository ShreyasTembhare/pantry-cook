"""POST /api/items/sentence previews, then saves the whole batch or nothing."""

from collections.abc import Generator
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_db, get_sentence_llm
from app.graph.llm import FakeMealModel
from app.main import create_app
from app.schemas.quick_add import DraftPantryLine, DraftPantrySentence


@pytest.fixture
def client(session_factory: sessionmaker[Session]) -> Generator[TestClient, None, None]:
    def override_db() -> Generator[Session, None, None]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_db

    with TestClient(app) as test_client:
        yield test_client


def _preview(client: TestClient, sentence: str) -> object:
    return client.post("/api/items/sentence/preview", json={"sentence": sentence})


def _save(client: TestClient, items: list[dict[str, str]]) -> object:
    return client.post("/api/items/sentence", json={"items": items})


class TestSentencePreview:
    def test_preview_parses_without_writing(self, client: TestClient) -> None:
        response = _preview(client, "2 leeks and 500 g chicken")
        assert response.status_code == 200, response.text
        body = response.json()
        assert [(row["name"], row["unit"], row["action"]) for row in body["items"]] == [
            ("Leeks", "count", "create"),
            ("Chicken", "g", "create"),
        ]
        assert Decimal(body["items"][1]["quantity"]) == Decimal("500")
        assert client.get("/api/items").json() == []

    def test_bad_sentence_is_a_problem(self, client: TestClient) -> None:
        response = _preview(client, "hello pantry")
        assert response.status_code == 422
        assert response.headers["content-type"] == "application/problem+json"
        body = response.json()
        assert body["code"] == "sentence_unparsed"
        assert "hello pantry" in body["detail"]
        assert client.get("/api/items").json() == []

    def test_fractional_count_writes_nothing(self, client: TestClient) -> None:
        response = _preview(client, "1.5 eggs and 500 g chicken")
        assert response.status_code == 422
        assert response.json()["code"] == "non_integer_count"
        assert client.get("/api/items").json() == []

    def test_blank_sentence_is_validation(self, client: TestClient) -> None:
        response = _preview(client, "   ")
        assert response.status_code == 422
        assert response.json()["code"] == "validation_failed"


class TestSentenceSave:
    def test_save_adds_the_previewed_items(self, client: TestClient) -> None:
        preview = _preview(client, "2 leeks and 500 g chicken")
        assert preview.status_code == 200
        items = [
            {"name": row["name"], "quantity": row["quantity"], "unit": row["unit"]}
            for row in preview.json()["items"]
        ]
        saved = _save(client, items)
        assert saved.status_code == 200, saved.text
        names = {row["name"]: row for row in saved.json()}
        assert Decimal(names["Leeks"]["quantity"]) == Decimal("2")
        assert names["Leeks"]["unit"] == "count"
        assert Decimal(names["Chicken"]["quantity"]) == Decimal("500")
        assert names["Chicken"]["dimension"] == "mass"
        listed = client.get("/api/items").json()
        assert {row["name"] for row in listed} == {"Leeks", "Chicken"}

    def test_save_merges_same_dimension(self, client: TestClient) -> None:
        created = client.post("/api/items", json={"name": "Rice", "quantity": "500", "unit": "g"})
        assert created.status_code == 201
        saved = _save(client, [{"name": "rice", "quantity": "1", "unit": "kg"}])
        assert saved.status_code == 200, saved.text
        body = saved.json()
        assert len(body) == 1
        assert Decimal(body[0]["quantity"]) == Decimal("1500")
        assert body[0]["unit"] == "g"

    def test_clash_does_not_keep_the_earlier_item(self, client: TestClient) -> None:
        created = client.post(
            "/api/items", json={"name": "Chicken", "quantity": "2", "unit": "count"}
        )
        assert created.status_code == 201
        saved = _save(
            client,
            [
                {"name": "Leeks", "quantity": "2", "unit": "count"},
                {"name": "Chicken", "quantity": "500", "unit": "g"},
            ],
        )
        assert saved.status_code == 422
        assert saved.json()["code"] == "sentence_unparsed"
        listed = client.get("/api/items").json()
        assert [row["name"] for row in listed] == ["Chicken"]
        assert Decimal(listed[0]["quantity"]) == Decimal("2")

    def test_bad_model_output_does_not_write(self, client: TestClient) -> None:
        client.app.dependency_overrides[get_sentence_llm] = lambda: FakeMealModel(script=["nope"])
        response = _preview(client, "something tasty please")
        assert response.status_code == 422
        assert response.json()["code"] == "sentence_unparsed"
        assert client.get("/api/items").json() == []

    def test_scripted_invalid_batch_does_not_write(self, client: TestClient) -> None:
        client.app.dependency_overrides[get_sentence_llm] = lambda: FakeMealModel(
            script=[
                DraftPantrySentence(
                    items=[
                        DraftPantryLine(name="Eggs", quantity=Decimal("1.5"), unit="count"),
                        DraftPantryLine(name="Chicken", quantity=Decimal("500"), unit="g"),
                    ]
                )
            ]
        )
        response = _preview(client, "1.5 eggs and chicken")
        assert response.status_code == 422
        assert response.json()["code"] == "non_integer_count"
        assert client.get("/api/items").json() == []
