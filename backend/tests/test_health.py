from fastapi.testclient import TestClient

from autofgo.main import app
from tests.helpers import authentication_headers


def test_health() -> None:
    response = TestClient(app).get("/api/health", headers=authentication_headers())

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
