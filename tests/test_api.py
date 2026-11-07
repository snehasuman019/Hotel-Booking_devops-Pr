
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_home():
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["status"] == "running"


def test_health():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_get_rooms():
    response = client.get("/rooms")

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_invalid_room():
    response = client.get("/rooms/99999")

    assert response.status_code == 404


def test_invalid_availability_dates():
    response = client.get(
        "/availability",
        params={
            "check_in": "2026-11-15",
            "check_out": "2026-11-10"
        }
    )

    assert response.status_code == 400
