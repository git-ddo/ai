from fastapi.testclient import TestClient

from app.main import create_app

client = TestClient(create_app())


def test_health_returns_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200


def test_health_returns_expected_payload() -> None:
    response = client.get("/health")

    assert response.json() == {"status": "UP"}


def test_unknown_path_returns_not_found() -> None:
    response = client.get("/unknown")

    assert response.status_code == 404


def test_docs_are_accessible_and_include_health_api() -> None:
    docs_response = client.get("/docs")
    openapi_response = client.get("/openapi.json")

    assert docs_response.status_code == 200
    assert openapi_response.status_code == 200
    assert "/health" in openapi_response.json()["paths"]
