from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


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


OperationHandler = Callable[[ScenarioCommand], None]


def _skill_handler(command: ScenarioCommand) -> None:
    if not isinstance(command, SkillCommand):
        raise TypeError("skill handler received an incompatible command")


def _master_skill_handler(command: ScenarioCommand) -> None:
    if not isinstance(command, MasterSkillCommand):
        raise TypeError("master_skill handler received an incompatible command")


def _attack_handler(command: ScenarioCommand) -> None:
    if not isinstance(command, AttackCommand):
        raise TypeError("attack handler received an incompatible command")


def _swap_handler(command: ScenarioCommand) -> None:
    if not isinstance(command, SwapCommand):
        raise TypeError("swap handler received an incompatible command")


# This table is deliberately source-defined. Request values are never used as Python names.
COMMAND_HANDLERS: dict[str, OperationHandler] = {
    "skill": _skill_handler,
    "master_skill": _master_skill_handler,
    "attack": _attack_handler,
    "swap": _swap_handler,
}


class CommandConflictError(Exception):
    def __init__(self, command_id: str) -> None:
        self.command_id = command_id


class AcceptedCommand(BaseModel):
    request: CommandRequest
    accepted_at: datetime
    handler: OperationHandler


class CommandRegistry:
    """Holds accepted commands until R07 replaces storage with the execution queue."""

    def __init__(self) -> None:
        self._commands: dict[str, AcceptedCommand] = {}

    def accept(self, command_request: CommandRequest) -> tuple[AcceptedCommand, bool]:
        existing = self._commands.get(command_request.command_id)
        if existing is not None:
            if existing.request.command != command_request.command:
                raise CommandConflictError(command_request.command_id)
            return existing, True

        handler = COMMAND_HANDLERS[command_request.command.type]
        accepted = AcceptedCommand(
            request=command_request,
            accepted_at=datetime.now(UTC),
            handler=handler,
        )
        self._commands[command_request.command_id] = accepted
        return accepted, False


_command_registry = CommandRegistry()


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
        "commandId": accepted.request.command_id,
        "status": "queued",
        "acceptedAt": _format_datetime(accepted.accepted_at),
    }
    if duplicate:
        data["duplicate"] = True
    return JSONResponse(status_code=200 if duplicate else 202, content={"data": data})


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
