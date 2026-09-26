import pytest
from fastapi.testclient import TestClient

from autofgo.commands import COMMAND_HANDLERS, CommandRegistry, get_command_registry
from autofgo.main import app
from tests.helpers import authentication_headers

COMMAND_ID = "0195d84e-7c82-7a31-a261-a1db5a3f7190"


@pytest.fixture
def client() -> TestClient:
    registry = CommandRegistry()
    app.dependency_overrides[get_command_registry] = lambda: registry
    yield TestClient(app, headers=authentication_headers())
    app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "command",
    [
        {"type": "skill", "skillIndex": 8, "targetIndex": 5},
        {"type": "master_skill", "skillIndex": 2, "targetIndex": 2},
        {"type": "attack", "noblePhantasmIndexes": [2, 0, 1]},
        {"type": "swap", "frontIndex": 2, "backIndex": 5},
    ],
)
def test_accepts_each_fixed_command_type(client: TestClient, command: dict[str, object]) -> None:
    response = client.post("/api/commands", json={"commandId": COMMAND_ID, "command": command})

    assert response.status_code == 202
    assert response.json()["data"]["status"] == "queued"
    assert response.json()["data"]["acceptedAt"].endswith("Z")


def test_same_request_is_returned_as_duplicate_without_accepting_twice(client: TestClient) -> None:
    payload = {
        "commandId": COMMAND_ID,
        "command": {"type": "attack", "noblePhantasmIndexes": []},
    }

    assert client.post("/api/commands", json=payload).status_code == 202
    response = client.post("/api/commands", json=payload)

    assert response.status_code == 200
    assert response.json()["data"]["duplicate"] is True


def test_same_id_with_different_command_is_rejected(client: TestClient) -> None:
    first = {"commandId": COMMAND_ID, "command": {"type": "skill", "skillIndex": 0}}
    second = {"commandId": COMMAND_ID, "command": {"type": "skill", "skillIndex": 1}}

    assert client.post("/api/commands", json=first).status_code == 202
    response = client.post("/api/commands", json=second)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "COMMAND_ID_CONFLICT"


@pytest.mark.parametrize(
    "payload",
    [
        {"commandId": COMMAND_ID, "command": {"type": "unknown"}},
        {
            "commandId": COMMAND_ID,
            "command": {"type": "skill", "skillIndex": 0, "function": "danger"},
        },
        {"commandId": COMMAND_ID, "command": {"type": "attack", "noblePhantasmIndexes": [0, 0]}},
        {"commandId": COMMAND_ID, "command": {"type": "swap", "frontIndex": 3, "backIndex": 2}},
        {"commandId": COMMAND_ID, "command": {"type": "master_skill", "skillIndex": 3}},
        {"commandId": "not-a-uuid", "command": {"type": "skill", "skillIndex": 0}},
    ],
)
def test_rejects_unknown_or_invalid_input(client: TestClient, payload: dict[str, object]) -> None:
    response = client.post("/api/commands", json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_rejects_malformed_json_with_common_error(client: TestClient) -> None:
    response = client.post(
        "/api/commands", content=b'{"commandId":', headers={"content-type": "application/json"}
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_JSON"


def test_dispatch_table_contains_only_supported_commands() -> None:
    assert set(COMMAND_HANDLERS) == {"skill", "master_skill", "attack", "swap"}


def test_status_reports_queue_state(client: TestClient) -> None:
    response = client.get("/api/commands/status")

    assert response.status_code == 200
    assert response.json()["data"] == {
        "state": "idle",
        "currentCommandId": None,
        "queuedCount": 0,
        "acceptingCommands": True,
    }


def test_invalid_control_transition_returns_common_error(client: TestClient) -> None:
    response = client.post("/api/commands/pause")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATE"
    assert response.json()["error"]["details"]["currentState"] == "idle"


def test_start_control_moves_idle_execution_to_running(client: TestClient) -> None:
    response = client.post("/api/commands/start")

    assert response.status_code == 200
    assert response.json()["data"]["state"] == "running"


def test_complete_control_moves_empty_running_execution_to_completed(client: TestClient) -> None:
    assert client.post("/api/commands/start").status_code == 200

    response = client.post("/api/commands/complete")

    assert response.status_code == 200
    assert response.json()["data"]["state"] == "completed"
