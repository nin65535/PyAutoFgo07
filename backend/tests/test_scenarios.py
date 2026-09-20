import base64
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from autofgo.main import app
from autofgo.scenarios import ScenarioRepository, get_scenario_repository

FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures" / "scenarios"


@pytest.fixture
def scenario_directory() -> Path:
    directory = FIXTURE_DIRECTORY
    app.dependency_overrides[get_scenario_repository] = lambda: ScenarioRepository(directory)
    yield directory
    app.dependency_overrides.clear()


def test_list_scenarios_returns_only_lowercase_json_sorted_by_display_name(
    scenario_directory: Path,
) -> None:
    response = TestClient(app).get("/api/scenarios")

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

    response = TestClient(app).get(f"/api/scenarios/{_scenario_id('Alpha.json')}")

    assert response.status_code == 200
    assert response.json()["data"]["displayName"] == "Alpha"
    assert response.json()["data"]["content"] == expected


@pytest.mark.parametrize("scenario_id", ["missing", "Li4vc2VjcmV0Lmpzb24", "bm90ZXMudHh0"])
def test_get_scenario_hides_invalid_or_outside_paths(
    scenario_directory: Path, scenario_id: str
) -> None:
    response = TestClient(app).get(f"/api/scenarios/{scenario_id}")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "SCENARIO_NOT_FOUND",
            "message": "操作手順が見つかりません。",
        }
    }


def test_get_scenario_distinguishes_invalid_json(scenario_directory: Path) -> None:
    response = TestClient(app).get(f"/api/scenarios/{_scenario_id('broken.json')}")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "SCENARIO_INVALID_JSON"


def test_list_scenarios_returns_empty_list_when_directory_does_not_exist(
    scenario_directory: Path,
) -> None:
    app.dependency_overrides[get_scenario_repository] = lambda: ScenarioRepository(
        scenario_directory / "missing"
    )
    try:
        response = TestClient(app).get("/api/scenarios")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"data": {"scenarios": []}}


def _scenario_id(filename: str) -> str:
    return base64.urlsafe_b64encode(filename.encode()).decode().rstrip("=")
