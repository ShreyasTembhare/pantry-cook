"""Unexpected failures and bad query values use problem+json."""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_db
from app.config import Settings
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


def test_fractional_count_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/items",
        json={"name": "Eggs", "quantity": "1.5", "unit": "count"},
    )
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["code"] == "non_integer_count"
    assert "Traceback" not in response.text


def test_unknown_sort_is_rejected(client: TestClient) -> None:
    response = client.get("/api/items?sort=nope")
    assert response.status_code == 422
    assert response.json()["code"] == "validation_failed"


def test_unknown_meal_status_is_rejected(client: TestClient) -> None:
    response = client.get("/api/meals?status=nope")
    assert response.status_code == 422
    assert response.json()["code"] == "validation_failed"


def test_item_create_documents_problem_details(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    documented = schema["paths"]["/api/items"]["post"]["responses"]
    assert documented["422"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/ProblemDetails"
    )
    assert documented["500"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/ProblemDetails"
    )
    assert documented["503"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/ProblemDetails"
    )


def test_database_outage_is_unavailable() -> None:
    def override_db() -> Session:
        raise OperationalError("connect", None, Exception("connection refused"))

    app = create_app()
    app.dependency_overrides[get_db] = override_db
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/items")
    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "database_unavailable"
    assert "connection refused" not in response.text
    assert "Traceback" not in response.text


def test_unexpected_error_hides_the_traceback() -> None:
    def override_db() -> Session:
        raise RuntimeError("secret stack detail")

    app = create_app()
    app.dependency_overrides[get_db] = override_db
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/items")
    assert response.status_code == 500
    body = response.json()
    assert body["code"] == "internal_error"
    assert body["detail"] == "Something went wrong."
    assert "secret stack detail" not in response.text
    assert "Traceback" not in response.text


def test_settings_read_env_and_the_unprefixed_openai_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PANTRY_ENV", "production")
    monkeypatch.setenv("PANTRY_MAINTENANCE", "off")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("PANTRY_OPENAI_API_KEY", raising=False)
    cfg = Settings()
    assert cfg.env == "production"
    assert cfg.maintenance is False
    assert cfg.openai_api_key == "sk-test"
    assert not hasattr(cfg, "host")
    assert not hasattr(cfg, "port")
