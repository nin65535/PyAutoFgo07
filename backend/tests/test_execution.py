from __future__ import annotations

import time
from collections.abc import Callable
from threading import Event

import pytest

from autofgo.execution import (
    CommandState,
    ExecutionControl,
    ExecutionManager,
    ExecutionState,
    InvalidExecutionStateError,
    QueuedCommand,
)


def wait_until(predicate: Callable[[], bool], timeout: float = 1.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError("condition was not reached")
        time.sleep(0.005)


def test_commands_are_executed_one_at_a_time_in_acceptance_order() -> None:
    manager = ExecutionManager()
    release_first = Event()
    calls: list[str] = []

    def handler(value: str, control: ExecutionControl) -> str:
        calls.append(value)
        if value == "first":
            release_first.wait(1)
        return value.upper()

    first = QueuedCommand("first", "first", handler)
    second = QueuedCommand("second", "second", handler)
    manager.enqueue(first)
    manager.enqueue(second)

    wait_until(lambda: first.state == CommandState.RUNNING)
    assert second.state == CommandState.QUEUED
    release_first.set()
    wait_until(lambda: second.state == CommandState.COMPLETED)

    assert calls == ["first", "second"]
    assert first.result == "FIRST"
    assert second.result == "SECOND"
    manager.close()


def test_pause_keeps_waiting_command_queued_until_resume() -> None:
    manager = ExecutionManager()
    gate = Event()

    def blocking_handler(value: str, control: ExecutionControl) -> None:
        gate.wait(1)

    first = QueuedCommand("first", "first", blocking_handler)
    second = QueuedCommand("second", "second", lambda value, control: None)
    manager.enqueue(first)
    manager.enqueue(second)
    wait_until(lambda: first.state == CommandState.RUNNING)

    manager.pause()
    gate.set()
    wait_until(lambda: manager.state == ExecutionState.PAUSED)
    assert second.state == CommandState.QUEUED

    manager.resume()
    wait_until(lambda: second.state == CommandState.COMPLETED)
    manager.close()


def test_normal_stop_cancels_current_and_pending_commands() -> None:
    manager = ExecutionManager()
    entered = Event()

    def cancellable_handler(value: str, control: ExecutionControl) -> None:
        entered.set()
        while not control.cancel_event.wait(0.005):
            pass

    current = QueuedCommand("current", "current", cancellable_handler)
    pending = QueuedCommand("pending", "pending", lambda value, control: None)
    manager.enqueue(current)
    manager.enqueue(pending)
    assert entered.wait(1)

    manager.stop()
    wait_until(lambda: manager.state == ExecutionState.STOPPED)

    assert current.state == CommandState.CANCELLED
    assert current.cancel_reason == "normal_stop"
    assert pending.state == CommandState.CANCELLED
    assert pending.cancel_reason == "normal_stop"
    manager.close()


def test_emergency_stop_immediately_discards_pending_commands() -> None:
    manager = ExecutionManager(start_worker=False)
    item = QueuedCommand("pending", "pending", lambda value, control: None)
    manager.enqueue(item)

    manager.emergency_stop()

    assert manager.state == ExecutionState.EMERGENCY_STOPPING
    assert item.state == CommandState.CANCELLED
    assert item.cancel_reason == "emergency_stop"
    assert manager.snapshot()["acceptingCommands"] is False


def test_emergency_stop_from_idle_disables_command_intake() -> None:
    manager = ExecutionManager(start_worker=False)

    manager.emergency_stop("chrome_process_exited")
    manager.emergency_stop("duplicate")

    assert manager.state == ExecutionState.EMERGENCY_STOPPING
    assert manager.snapshot()["acceptingCommands"] is False


def test_handler_failure_moves_execution_to_error_and_discards_following() -> None:
    manager = ExecutionManager()
    release_failure = Event()

    def fail(value: str, control: ExecutionControl) -> None:
        release_failure.wait(1)
        raise RuntimeError("sensitive detail")

    failed = QueuedCommand("failed", "failed", fail)
    following = QueuedCommand("following", "following", lambda value, control: None)
    manager.enqueue(failed)
    manager.enqueue(following)
    release_failure.set()
    wait_until(lambda: manager.state == ExecutionState.ERROR)

    assert failed.state == CommandState.FAILED
    assert failed.error == "RuntimeError"
    assert following.state == CommandState.CANCELLED
    assert following.cancel_reason == "execution_failed"
    manager.close()


def test_invalid_transition_is_rejected() -> None:
    manager = ExecutionManager(start_worker=False)

    with pytest.raises(InvalidExecutionStateError):
        manager.pause()


def test_start_allows_a_stopped_manager_to_accept_commands_again() -> None:
    manager = ExecutionManager(start_worker=False)
    manager.start()
    manager.stop()

    manager.start()
    item = QueuedCommand("next", "next", lambda value, control: None)
    manager.enqueue(item)

    assert manager.state == ExecutionState.RUNNING
    assert manager.snapshot()["acceptingCommands"] is True
