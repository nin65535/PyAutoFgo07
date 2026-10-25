import base64
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from autofgo.main import app
from autofgo.scenarios import ScenarioRepository, get_scenario_repository
from tests.helpers import authentication_headers

FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures" / "scenarios"


def client() -> TestClient:
    return TestClient(app, headers=authentication_headers())


@pytest.fixture
def scenario_directory() -> Path:
    directory = FIXTURE_DIRECTORY
    app.dependency_overrides[get_scenario_repository] = lambda: ScenarioRepository(directory)
    yield directory
    app.dependency_overrides.clear()


def test_list_scenarios_returns_only_lowercase_json_sorted_by_display_name(
    scenario_directory: Path,
) -> None:
    response = client().get("/api/scenarios")

    assert response.status_code == 200
    scenarios = response.json()["data"]["scenarios"]
    assert [item["displayName"] for item in scenarios] == ["Alpha", "beta", "broken"]
    assert all(item["modifiedAt"].endswith("Z") for item in scenarios)
    assert scenarios[0]["id"] == _scenario_id("Alpha.json")


def test_get_scenario_returns_metadata_and_unvalidated_json(scenario_directory: Path) -> None:
    expected = {
        "schemaVersion": 1,
        "members": ["A"],
        "commands": [["attack()"]],
    }

    response = client().get(f"/api/scenarios/{_scenario_id('Alpha.json')}")

    assert response.status_code == 200
    assert response.json()["data"]["displayName"] == "Alpha"
    assert response.json()["data"]["content"] == expected


@pytest.mark.integration
def test_scenario_api_reads_edited_file_on_next_request(tmp_path: Path) -> None:
    directory = tmp_path / "scenarios"
    directory.mkdir()
    path = directory / "editable.json"
    original = {"schemaVersion": 1, "members": ["Before"], "commands": [["attack()"]]}
    edited = {"schemaVersion": 1, "members": ["After"], "commands": [["skill(1)"]]}
    path.write_text(json.dumps(original), encoding="utf-8")
    app.dependency_overrides[get_scenario_repository] = lambda: ScenarioRepository(directory)
    try:
        listed = client().get("/api/scenarios")
        first = client().get(f"/api/scenarios/{_scenario_id(path.name)}")
        path.write_text(json.dumps(edited), encoding="utf-8")
        second = client().get(f"/api/scenarios/{_scenario_id(path.name)}")
    finally:
        app.dependency_overrides.clear()

    assert listed.headers["cache-control"] == "no-store"
    assert first.headers["cache-control"] == "no-store"
    assert second.headers["cache-control"] == "no-store"
    assert first.json()["data"]["content"] == original
    assert second.json()["data"]["content"] == edited


@pytest.mark.parametrize("scenario_id", ["missing", "Li4vc2VjcmV0Lmpzb24", "bm90ZXMudHh0"])
def test_get_scenario_hides_invalid_or_outside_paths(
    scenario_directory: Path, scenario_id: str
) -> None:
    response = client().get(f"/api/scenarios/{scenario_id}")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "SCENARIO_NOT_FOUND",
            "message": "操作手順が見つかりません。",
        }
    }


def test_get_scenario_distinguishes_invalid_json(scenario_directory: Path) -> None:
    response = client().get(f"/api/scenarios/{_scenario_id('broken.json')}")

    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["error"]["code"] == "SCENARIO_INVALID_JSON"


def test_list_scenarios_returns_empty_list_when_directory_does_not_exist(
    scenario_directory: Path,
) -> None:
    app.dependency_overrides[get_scenario_repository] = lambda: ScenarioRepository(
        scenario_directory / "missing"
    )
    try:
        response = client().get("/api/scenarios")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"data": {"scenarios": []}}


def _scenario_id(filename: str) -> str:
    return base64.urlsafe_b64encode(filename.encode()).decode().rstrip("=")
