import pytest
from fastapi.testclient import TestClient

from autofgo.config import Settings
from autofgo.main import app
from autofgo.security import SESSION_HEADER, SessionSecurity, session_security
from tests.helpers import authentication_headers


def test_api_rejects_missing_and_incorrect_credentials_without_leaking_token() -> None:
    client = TestClient(app)

    missing = client.get("/api/health")
    incorrect = client.get(
        "/api/health",
        headers={SESSION_HEADER: session_security.session_id, "Authorization": "Bearer wrong"},
    )

    assert missing.status_code == 401
    assert incorrect.status_code == 401
    assert session_security.token not in missing.text + incorrect.text


def test_api_rejects_unapproved_origin() -> None:
    response = TestClient(app).get(
        "/api/health", headers=authentication_headers(origin="http://evil.example")
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ORIGIN_FORBIDDEN"


def test_api_accepts_configured_frontend_origin_and_sets_cors_header() -> None:
    origin = "http://127.0.0.1:5173"
    response = TestClient(app).get("/api/health", headers=authentication_headers(origin=origin))

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin


def test_api_rejects_oversized_request_before_validation() -> None:
    response = TestClient(app).post(
        "/api/commands",
        headers={**authentication_headers(), "Content-Type": "application/json"},
        content=b"x" * (64 * 1024 + 1),
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "REQUEST_TOO_LARGE"


def test_api_rejects_unknown_query_and_body_inputs() -> None:
    client = TestClient(app, headers=authentication_headers())

    query_response = client.get("/api/health?unexpected=value")
    body_response = client.post("/api/commands/start", content=b"{}")

    assert query_response.status_code == 422
    assert body_response.status_code == 422
    assert query_response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_session_token_is_invalid_after_invalidation() -> None:
    security = SessionSecurity()
    token = security.token
    assert security.authenticate(security.session_id, f"Bearer {token}")

    security.invalidate()

    assert not security.authenticate(security.session_id, f"Bearer {token}")


def test_settings_reject_non_loopback_host() -> None:
    with pytest.raises(ValueError, match="loopback"):
        Settings(host="0.0.0.0")
