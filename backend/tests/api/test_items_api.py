"""Tests for the /api/items endpoints — CRUD, error responses."""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_db
from app.main import create_app


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

    with TestClient(app) as tc:
        yield tc


class TestCreateItem:
    def test_create_success(self, client: TestClient) -> None:
        resp = client.post(
            "/api/items",
            json={"name": "Rice", "quantity": "500", "unit": "g"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Rice"
        assert data["unit"] == "g"
        assert data["dimension"] == "mass"
        assert data["version"] == 1
        assert "id" in data

    def test_create_with_expiry(self, client: TestClient) -> None:
        resp = client.post(
            "/api/items",
            json={"name": "Milk", "quantity": "1", "unit": "L", "expires_on": "2025-03-15"},
        )
        assert resp.status_code == 201
        assert resp.json()["expires_on"] == "2025-03-15"

    def test_create_kg_stores_in_grams(self, client: TestClient) -> None:
        resp = client.post(
            "/api/items",
            json={"name": "Flour", "quantity": "1.5", "unit": "kg"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["quantity"] == "1.50"
        assert data["unit"] == "kg"

    def test_create_duplicate_409(self, client: TestClient) -> None:
        client.post("/api/items", json={"name": "Rice", "quantity": "500", "unit": "g"})
        resp = client.post("/api/items", json={"name": "rice", "quantity": "200", "unit": "g"})
        assert resp.status_code == 409
        body = resp.json()
        assert body["code"] == "duplicate_item"
        assert "existing_id" in body.get("extra", {})

    def test_create_blank_name_422(self, client: TestClient) -> None:
        resp = client.post("/api/items", json={"name": "   ", "quantity": "500", "unit": "g"})
        assert resp.status_code == 422
        body = resp.json()
        assert body["code"] == "validation_failed"

    def test_create_negative_quantity_422(self, client: TestClient) -> None:
        resp = client.post("/api/items", json={"name": "Rice", "quantity": "-1", "unit": "g"})
        assert resp.status_code == 422

    def test_request_id_in_response(self, client: TestClient) -> None:
        resp = client.post("/api/items", json={"name": "Rice", "quantity": "500", "unit": "g"})
        assert "x-request-id" in resp.headers

    def test_problem_details_content_type(self, client: TestClient) -> None:
        client.post("/api/items", json={"name": "Rice", "quantity": "500", "unit": "g"})
        resp = client.post("/api/items", json={"name": "rice", "quantity": "200", "unit": "g"})
        assert resp.headers["content-type"] == "application/problem+json"


class TestListItems:
    def test_list_empty(self, client: TestClient) -> None:
        resp = client.get("/api/items")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_returns_items(self, client: TestClient) -> None:
        client.post("/api/items", json={"name": "Rice", "quantity": "500", "unit": "g"})
        client.post("/api/items", json={"name": "Flour", "quantity": "1", "unit": "kg"})

        resp = client.get("/api/items")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2


class TestGetItem:
    def test_get_existing(self, client: TestClient) -> None:
        create_resp = client.post(
            "/api/items", json={"name": "Rice", "quantity": "500", "unit": "g"}
        )
        item_id = create_resp.json()["id"]

        resp = client.get(f"/api/items/{item_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Rice"

    def test_get_missing_404(self, client: TestClient) -> None:
        resp = client.get("/api/items/nonexistent")
        assert resp.status_code == 404
        body = resp.json()
        assert body["code"] == "item_not_found"


class TestUpdateItem:
    def test_update_name(self, client: TestClient) -> None:
        create_resp = client.post(
            "/api/items", json={"name": "Rice", "quantity": "500", "unit": "g"}
        )
        item_id = create_resp.json()["id"]

        resp = client.patch(f"/api/items/{item_id}", json={"name": "Brown Rice", "version": 1})
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Brown Rice"
        assert data["version"] == 2

    def test_update_quantity(self, client: TestClient) -> None:
        create_resp = client.post(
            "/api/items", json={"name": "Rice", "quantity": "500", "unit": "g"}
        )
        item_id = create_resp.json()["id"]

        resp = client.patch(f"/api/items/{item_id}", json={"quantity": "300", "version": 1})
        assert resp.status_code == 200
        assert resp.json()["quantity"] == "300.00"

    def test_clear_expiry(self, client: TestClient) -> None:
        create_resp = client.post(
            "/api/items",
            json={"name": "Milk", "quantity": "1", "unit": "L", "expires_on": "2026-10-02"},
        )
        item_id = create_resp.json()["id"]

        kept = client.patch(f"/api/items/{item_id}", json={"name": "Whole milk", "version": 1})
        assert kept.status_code == 200
        assert kept.json()["expires_on"] == "2026-10-02"

        cleared = client.patch(f"/api/items/{item_id}", json={"expires_on": None, "version": 2})
        assert cleared.status_code == 200
        assert cleared.json()["expires_on"] is None

    def test_update_stale_version_409(self, client: TestClient) -> None:
        create_resp = client.post(
            "/api/items", json={"name": "Rice", "quantity": "500", "unit": "g"}
        )
        item_id = create_resp.json()["id"]

        client.patch(f"/api/items/{item_id}", json={"name": "Brown Rice", "version": 1})
        resp = client.patch(f"/api/items/{item_id}", json={"name": "White Rice", "version": 1})
        assert resp.status_code == 409
        assert resp.json()["code"] == "stale_version"

    def test_update_missing_404(self, client: TestClient) -> None:
        resp = client.patch("/api/items/nonexistent", json={"name": "X", "version": 1})
        assert resp.status_code == 404

    def test_update_rename_to_duplicate_409(self, client: TestClient) -> None:
        client.post("/api/items", json={"name": "Rice", "quantity": "500", "unit": "g"})
        create_resp = client.post(
            "/api/items", json={"name": "Flour", "quantity": "1", "unit": "kg"}
        )
        item_id = create_resp.json()["id"]

        resp = client.patch(f"/api/items/{item_id}", json={"name": "Rice", "version": 1})
        assert resp.status_code == 409
        assert resp.json()["code"] == "duplicate_item"


class TestMergeItem:
    def test_adds_onto_the_existing_quantity(self, client: TestClient) -> None:
        created = client.post("/api/items", json={"name": "Rice", "quantity": "500", "unit": "g"})
        assert created.status_code == 201
        item_id = created.json()["id"]
        merged = client.post(f"/api/items/{item_id}/merge", json={"quantity": "0.25", "unit": "kg"})
        assert merged.status_code == 200, merged.text
        body = merged.json()
        assert body["quantity"] == "750.00"
        assert body["unit"] == "g"
        assert body["version"] == 2

    def test_rejects_a_different_dimension(self, client: TestClient) -> None:
        created = client.post("/api/items", json={"name": "Milk", "quantity": "1", "unit": "L"})
        merged = client.post(
            f"/api/items/{created.json()['id']}/merge",
            json={"quantity": "200", "unit": "g"},
        )
        assert merged.status_code == 422
        assert merged.json()["code"] == "unit_dimension_mismatch"

    def test_rejects_a_quantity_past_the_limit(self, client: TestClient) -> None:
        created = client.post(
            "/api/items", json={"name": "Flour", "quantity": "1000000", "unit": "g"}
        )
        merged = client.post(
            f"/api/items/{created.json()['id']}/merge",
            json={"quantity": "1", "unit": "g"},
        )
        assert merged.status_code == 422
        assert merged.json()["code"] == "quantity_limit"


class TestDeleteItem:
    def test_delete_success(self, client: TestClient) -> None:
        create_resp = client.post(
            "/api/items", json={"name": "Rice", "quantity": "500", "unit": "g"}
        )
        item_id = create_resp.json()["id"]

        resp = client.delete(f"/api/items/{item_id}")
        assert resp.status_code == 204

        resp = client.get(f"/api/items/{item_id}")
        assert resp.status_code == 404

    def test_delete_missing_404(self, client: TestClient) -> None:
        resp = client.delete("/api/items/nonexistent")
        assert resp.status_code == 404
