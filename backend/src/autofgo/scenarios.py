import base64
import binascii
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from autofgo.config import Settings, get_settings

router = APIRouter(prefix="/api/scenarios", tags=["scenarios"])
MAX_SCENARIO_FILE_BYTES = 1024 * 1024


class ScenarioError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message


class ScenarioRepository:
    def __init__(self, directory: Path) -> None:
        self.directory = directory.resolve()

    def list(self) -> list[dict[str, str]]:
        if not self.directory.exists():
            return []
        if not self.directory.is_dir():
            raise ScenarioError(500, "SCENARIO_READ_FAILED", "操作手順一覧を読み取れません。")

        scenarios: list[dict[str, str]] = []
        try:
            entries = list(self.directory.iterdir())
        except OSError as error:
            raise ScenarioError(
                500, "SCENARIO_READ_FAILED", "操作手順一覧を読み取れません。"
            ) from error

        for path in entries:
            if not path.is_file() or path.suffix != ".json":
                continue
            try:
                modified_at = _format_datetime(path.stat().st_mtime)
            except OSError as error:
                raise ScenarioError(
                    500, "SCENARIO_READ_FAILED", "操作手順一覧を読み取れません。"
                ) from error
            scenarios.append(
                {
                    "id": _encode_id(path.name),
                    "displayName": path.stem,
                    "modifiedAt": modified_at,
                }
            )

        return sorted(
            scenarios,
            key=lambda scenario: (scenario["displayName"].casefold(), scenario["id"]),
        )

    def get(self, scenario_id: str) -> tuple[dict[str, str], Any]:
        filename = _decode_id(scenario_id)
        path = (self.directory / filename).resolve()
        if path.parent != self.directory or path.suffix != ".json":
            raise _not_found()

        try:
            if not path.is_file():
                raise _not_found()
            if path.stat().st_size > MAX_SCENARIO_FILE_BYTES:
                raise ScenarioError(
                    413, "SCENARIO_TOO_LARGE", "操作手順のサイズが上限を超えています。"
                )
            raw_content = path.read_text(encoding="utf-8")
            modified_at = _format_datetime(path.stat().st_mtime)
        except ScenarioError:
            raise
        except (OSError, UnicodeError) as error:
            raise ScenarioError(
                500, "SCENARIO_READ_FAILED", "操作手順を読み取れません。"
            ) from error

        try:
            content = json.loads(raw_content)
        except json.JSONDecodeError as error:
            raise ScenarioError(
                422, "SCENARIO_INVALID_JSON", "操作手順のJSONが不正です。"
            ) from error

        return (
            {"id": scenario_id, "displayName": path.stem, "modifiedAt": modified_at},
            content,
        )


def get_scenario_repository(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ScenarioRepository:
    return ScenarioRepository(settings.scenario_directory)


Repository = Annotated[ScenarioRepository, Depends(get_scenario_repository)]


@router.get("")
def list_scenarios(repository: Repository) -> dict[str, Any]:
    return {"data": {"scenarios": repository.list()}}


@router.get("/{scenario_id}")
def get_scenario(scenario_id: str, repository: Repository) -> dict[str, Any]:
    metadata, content = repository.get(scenario_id)
    return {"data": {**metadata, "content": content}}


async def scenario_error_handler(_request: Request, error: ScenarioError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={"error": {"code": error.code, "message": error.message}},
    )


def _encode_id(filename: str) -> str:
    return base64.urlsafe_b64encode(filename.encode("utf-8")).decode("ascii").rstrip("=")


def _decode_id(scenario_id: str) -> str:
    if not scenario_id or len(scenario_id) > 344:
        raise _not_found()
    try:
        padding = "=" * (-len(scenario_id) % 4)
        filename = base64.b64decode(scenario_id + padding, altchars=b"-_", validate=True).decode(
            "utf-8"
        )
    except (binascii.Error, UnicodeDecodeError) as error:
        raise _not_found() from error
    if _encode_id(filename) != scenario_id or Path(filename).name != filename:
        raise _not_found()
    return filename


def _format_datetime(timestamp: float) -> str:
    value = datetime.fromtimestamp(timestamp, UTC).isoformat(timespec="milliseconds")
    return value.replace("+00:00", "Z")


def _not_found() -> ScenarioError:
    return ScenarioError(404, "SCENARIO_NOT_FOUND", "操作手順が見つかりません。")
