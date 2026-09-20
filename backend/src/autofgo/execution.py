from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from threading import Condition, Event, Thread
from typing import Any


class ExecutionState(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSING = "pausing"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    COMPLETED = "completed"
    ERROR = "error"
    EMERGENCY_STOPPING = "emergency_stopping"


class CommandState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class InvalidExecutionStateError(Exception):
    def __init__(self, current: ExecutionState, required: tuple[ExecutionState, ...]) -> None:
        self.current = current
        self.required = required


class ExecutionUnavailableError(Exception):
    pass


@dataclass(slots=True)
class ExecutionControl:
    cancel_event: Event
    _manager: ExecutionManager

    def checkpoint(self) -> None:
        self._manager.wait_if_paused()
        if self.cancel_event.is_set():
            raise CommandCancelledError


class CommandCancelledError(Exception):
    pass


CommandHandler = Callable[[Any, ExecutionControl], Any]


@dataclass(slots=True)
class QueuedCommand:
    command_id: str
    command: Any
    handler: CommandHandler
    accepted_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    state: CommandState = CommandState.QUEUED
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result: Any = None
    error: str | None = None
    cancel_reason: str | None = None


class ExecutionManager:
    """Serial command queue with cooperative pause and priority cancellation."""

    def __init__(self, *, start_worker: bool = True) -> None:
        self._condition = Condition()
        self._commands: dict[str, QueuedCommand] = {}
        self._pending: deque[str] = deque()
        self._current: QueuedCommand | None = None
        self._state = ExecutionState.IDLE
        self._accepting = True
        self._shutdown = False
        self._cancel_event = Event()
        self._worker: Thread | None = None
        if start_worker:
            self._worker = Thread(target=self._run, name="command-queue", daemon=True)
            self._worker.start()

    @property
    def state(self) -> ExecutionState:
        with self._condition:
            return self._state

    def get(self, command_id: str) -> QueuedCommand | None:
        with self._condition:
            return self._commands.get(command_id)

    def enqueue(self, item: QueuedCommand) -> tuple[QueuedCommand, bool]:
        with self._condition:
            existing = self._commands.get(item.command_id)
            if existing is not None:
                return existing, True
            if not self._accepting:
                raise ExecutionUnavailableError
            if self._state in {ExecutionState.IDLE, ExecutionState.COMPLETED}:
                self._state = ExecutionState.RUNNING
            elif self._state not in {ExecutionState.RUNNING}:
                raise InvalidExecutionStateError(self._state, (ExecutionState.RUNNING,))
            self._commands[item.command_id] = item
            self._pending.append(item.command_id)
            self._condition.notify_all()
            return item, False

    def pause(self) -> None:
        with self._condition:
            self._require(ExecutionState.RUNNING)
            self._state = ExecutionState.PAUSING if self._current else ExecutionState.PAUSED
            self._condition.notify_all()

    def resume(self) -> None:
        with self._condition:
            self._require(ExecutionState.PAUSED, ExecutionState.PAUSING)
            self._state = ExecutionState.RUNNING
            self._condition.notify_all()

    def stop(self) -> None:
        self._cancel("normal_stop", emergency=False)

    def emergency_stop(self, reason: str = "emergency_stop") -> None:
        self._cancel(reason, emergency=True)

    def complete(self) -> None:
        with self._condition:
            self._require(ExecutionState.RUNNING)
            if self._current is not None or self._pending:
                raise InvalidExecutionStateError(self._state, (ExecutionState.RUNNING,))
            self._state = ExecutionState.COMPLETED

    def wait_if_paused(self) -> None:
        with self._condition:
            if self._state == ExecutionState.PAUSING:
                self._state = ExecutionState.PAUSED
                self._condition.notify_all()
            while self._state == ExecutionState.PAUSED and not self._cancel_event.is_set():
                self._condition.wait()

    def snapshot(self) -> dict[str, object]:
        with self._condition:
            return {
                "state": self._state.value,
                "currentCommandId": self._current.command_id if self._current else None,
                "queuedCount": len(self._pending),
                "acceptingCommands": self._accepting,
            }

    def close(self) -> None:
        with self._condition:
            self._shutdown = True
            self._cancel_event.set()
            self._condition.notify_all()
        if self._worker:
            self._worker.join(timeout=1)

    def _cancel(self, reason: str, *, emergency: bool) -> None:
        with self._condition:
            allowed = (
                ExecutionState.RUNNING,
                ExecutionState.PAUSING,
                ExecutionState.PAUSED,
                ExecutionState.STOPPING,
            )
            if self._state not in allowed:
                raise InvalidExecutionStateError(self._state, allowed)
            self._accepting = False
            self._state = (
                ExecutionState.EMERGENCY_STOPPING if emergency else ExecutionState.STOPPING
            )
            self._cancel_event.set()
            now = datetime.now(UTC)
            while self._pending:
                item = self._commands[self._pending.popleft()]
                item.state = CommandState.CANCELLED
                item.cancel_reason = reason
                item.finished_at = now
            if self._current is not None:
                self._current.cancel_reason = reason
            if not emergency and self._current is None:
                self._state = ExecutionState.STOPPED
            self._condition.notify_all()

    def _run(self) -> None:
        while True:
            with self._condition:
                while not self._shutdown and (
                    not self._pending or self._state != ExecutionState.RUNNING
                ):
                    self._condition.wait()
                if self._shutdown:
                    return
                item = self._commands[self._pending.popleft()]
                self._current = item
                item.state = CommandState.RUNNING
                item.started_at = datetime.now(UTC)
            try:
                item.result = item.handler(item.command, ExecutionControl(self._cancel_event, self))
                if self._cancel_event.is_set():
                    raise CommandCancelledError
            except CommandCancelledError:
                item.state = CommandState.CANCELLED
                item.cancel_reason = item.cancel_reason or "normal_stop"
            except Exception as error:  # worker boundary: retain a safe summary only
                item.state = CommandState.FAILED
                item.error = type(error).__name__
                with self._condition:
                    self._state = ExecutionState.ERROR
                    self._accepting = False
                    self._cancel_pending("execution_failed")
            else:
                item.state = CommandState.COMPLETED
            finally:
                item.finished_at = datetime.now(UTC)
                with self._condition:
                    self._current = None
                    if self._state == ExecutionState.PAUSING:
                        self._state = ExecutionState.PAUSED
                    elif self._state == ExecutionState.STOPPING:
                        self._state = ExecutionState.STOPPED
                    self._condition.notify_all()

    def _cancel_pending(self, reason: str) -> None:
        now = datetime.now(UTC)
        while self._pending:
            item = self._commands[self._pending.popleft()]
            item.state = CommandState.CANCELLED
            item.cancel_reason = reason
            item.finished_at = now

    def _require(self, *states: ExecutionState) -> None:
        if self._state not in states:
            raise InvalidExecutionStateError(self._state, states)
