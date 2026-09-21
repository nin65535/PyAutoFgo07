from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from autofgo.events import event_broker
from autofgo.execution import (
    ExecutionControl,
    ExecutionManager,
    ExecutionUnavailableError,
    InvalidExecutionStateError,
    QueuedCommand,
)


class CommandModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SkillCommand(CommandModel):
    type: Literal["skill"]
    skill_index: int = Field(alias="skillIndex", ge=0, le=8)
    target_index: int | None = Field(default=None, alias="targetIndex", ge=0, le=5)


class MasterSkillCommand(CommandModel):
    type: Literal["master_skill"]
    skill_index: int = Field(alias="skillIndex", ge=0, le=3)
    target_index: int | None = Field(default=None, alias="targetIndex", ge=0, le=2)


class AttackCommand(CommandModel):
    type: Literal["attack"]
    noble_phantasm_indexes: list[int] = Field(
        alias="noblePhantasmIndexes", min_length=0, max_length=3
    )

    @model_validator(mode="after")
    def validate_indexes(self) -> AttackCommand:
        if any(index < 0 or index > 2 for index in self.noble_phantasm_indexes):
            raise ValueError("宝具インデックスは0以上2以下で指定してください。")
        if len(set(self.noble_phantasm_indexes)) != len(self.noble_phantasm_indexes):
            raise ValueError("宝具インデックスを重複して指定できません。")
        return self


class SwapCommand(CommandModel):
    type: Literal["swap"]
    front_index: int = Field(alias="frontIndex", ge=0, le=2)
    back_index: int = Field(alias="backIndex", ge=3, le=5)


ScenarioCommand = Annotated[
    SkillCommand | MasterSkillCommand | AttackCommand | SwapCommand,
    Field(discriminator="type"),
]
CommandId = Annotated[
    str,
    StringConstraints(
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
    ),
]


class CommandRequest(CommandModel):
    command_id: CommandId = Field(alias="commandId")
    command: ScenarioCommand


def _skill_handler(command: ScenarioCommand, control: ExecutionControl) -> None:
    control.checkpoint()
    if not isinstance(command, SkillCommand):
        raise TypeError("skill handler received an incompatible command")


def _master_skill_handler(command: ScenarioCommand, control: ExecutionControl) -> None:
    control.checkpoint()
    if not isinstance(command, MasterSkillCommand):
        raise TypeError("master_skill handler received an incompatible command")


def _attack_handler(command: ScenarioCommand, control: ExecutionControl) -> None:
    control.checkpoint()
    if not isinstance(command, AttackCommand):
        raise TypeError("attack handler received an incompatible command")


def _swap_handler(command: ScenarioCommand, control: ExecutionControl) -> None:
    control.checkpoint()
    if not isinstance(command, SwapCommand):
        raise TypeError("swap handler received an incompatible command")


# This table is deliberately source-defined. Request values are never used as Python names.
COMMAND_HANDLERS = {
    "skill": _skill_handler,
    "master_skill": _master_skill_handler,
    "attack": _attack_handler,
    "swap": _swap_handler,
}


class CommandConflictError(Exception):
    def __init__(self, command_id: str) -> None:
        self.command_id = command_id


class CommandRegistry:
    """Idempotent command intake backed by the serial execution queue."""

    def __init__(self, manager: ExecutionManager | None = None) -> None:
        self.manager = manager or ExecutionManager(start_worker=False)
        self._requests: dict[str, CommandRequest] = {}

    def accept(self, command_request: CommandRequest) -> tuple[QueuedCommand, bool]:
        existing_request = self._requests.get(command_request.command_id)
        if existing_request is not None:
            if existing_request.command != command_request.command:
                raise CommandConflictError(command_request.command_id)
            existing = self.manager.get(command_request.command_id)
            assert existing is not None
            return existing, True

        handler = COMMAND_HANDLERS[command_request.command.type]
        accepted = QueuedCommand(
            command_id=command_request.command_id,
            command=command_request.command,
            handler=handler,
        )
        queued, duplicate = self.manager.enqueue(accepted)
        self._requests[command_request.command_id] = command_request
        return queued, duplicate


_command_registry = CommandRegistry(
    ExecutionManager(
        event_sink=lambda event_type, data, command_id: event_broker.publish(
            event_type, data, command_id=command_id
        )
    )
)


def get_command_registry() -> CommandRegistry:
    return _command_registry


def _format_datetime(value: datetime) -> str:
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


router = APIRouter(prefix="/api/commands", tags=["commands"])
CommandRegistryDependency = Annotated[CommandRegistry, Depends(get_command_registry)]


@router.post("")
async def accept_command(
    command_request: CommandRequest,
    registry: CommandRegistryDependency,
) -> JSONResponse:
    accepted, duplicate = registry.accept(command_request)
    data: dict[str, object] = {
        "commandId": accepted.command_id,
        "status": accepted.state.value,
        "acceptedAt": _format_datetime(accepted.accepted_at),
    }
    if duplicate:
        data["duplicate"] = True
    return JSONResponse(status_code=200 if duplicate else 202, content={"data": data})


@router.get("/status")
async def execution_status(registry: CommandRegistryDependency) -> dict[str, object]:
    return {"data": registry.manager.snapshot()}


@router.post("/start")
async def start_execution(registry: CommandRegistryDependency) -> dict[str, object]:
    registry.manager.start()
    return {"data": registry.manager.snapshot()}


@router.post("/pause")
async def pause_execution(registry: CommandRegistryDependency) -> dict[str, object]:
    registry.manager.pause()
    return {"data": registry.manager.snapshot()}


@router.post("/resume")
async def resume_execution(registry: CommandRegistryDependency) -> dict[str, object]:
    registry.manager.resume()
    return {"data": registry.manager.snapshot()}


@router.post("/stop")
async def stop_execution(registry: CommandRegistryDependency) -> dict[str, object]:
    registry.manager.stop()
    return {"data": registry.manager.snapshot()}


@router.post("/emergency-stop")
async def emergency_stop_execution(registry: CommandRegistryDependency) -> dict[str, object]:
    registry.manager.emergency_stop()
    return {"data": registry.manager.snapshot()}


@router.post("/complete")
async def complete_execution(registry: CommandRegistryDependency) -> dict[str, object]:
    registry.manager.complete()
    return {"data": registry.manager.snapshot()}


async def command_conflict_handler(request: Request, error: CommandConflictError) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={
            "error": {
                "code": "COMMAND_ID_CONFLICT",
                "message": "同じ指令IDで異なる指令は受け付けられません。",
                "details": {"commandId": error.command_id},
            }
        },
    )


async def invalid_state_handler(
    request: Request, error: InvalidExecutionStateError
) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={
            "error": {
                "code": "INVALID_STATE",
                "message": "現在の実行状態ではこの操作を行えません。",
                "details": {
                    "currentState": error.current.value,
                    "requiredStates": [state.value for state in error.required],
                },
            }
        },
    )


async def unavailable_handler(request: Request, error: ExecutionUnavailableError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "error": {
                "code": "SERVICE_UNAVAILABLE",
                "message": "停止処理中のため指令を受け付けられません。",
            }
        },
    )
