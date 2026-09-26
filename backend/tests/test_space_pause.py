from __future__ import annotations

from threading import Event

from autofgo.execution import ExecutionControl, ExecutionManager, ExecutionState, QueuedCommand
from autofgo.space_pause import GlobalSpacePause


def test_space_press_pauses_only_while_running_and_only_once_per_keydown() -> None:
    manager = ExecutionManager(start_worker=False)
    pressed = False
    reads = 0

    def is_pressed() -> bool:
        nonlocal reads
        reads += 1
        return pressed

    monitor = GlobalSpacePause(manager, is_pressed=is_pressed)

    pressed = True
    monitor.poll_once()
    assert manager.state == ExecutionState.IDLE
    assert reads == 0

    pressed = False
    monitor.poll_once()
    manager.start()
    pressed = True
    monitor.poll_once()
    assert manager.state == ExecutionState.PAUSED

    pressed = False
    monitor.poll_once()
    pressed = True
    monitor.poll_once()
    assert manager.state == ExecutionState.PAUSED

    manager.resume()
    monitor.poll_once()
    assert manager.state == ExecutionState.PAUSED

    pressed = False
    monitor.poll_once()
    manager.resume()
    monitor.poll_once()
    assert manager.state == ExecutionState.RUNNING
    pressed = True
    monitor.poll_once()
    assert manager.state == ExecutionState.PAUSED
    manager.close()


def test_space_is_checked_immediately_before_the_next_click_checkpoint() -> None:
    manager = ExecutionManager()
    pressed = False
    monitor = GlobalSpacePause(manager, is_pressed=lambda: pressed)
    manager.set_pause_input_check(monitor.poll_once)
    at_checkpoint = Event()
    continue_command = Event()
    clicked = Event()

    def command(_value: object, control: ExecutionControl) -> None:
        at_checkpoint.set()
        assert continue_command.wait(1)
        control.checkpoint()
        clicked.set()

    manager.start()
    manager.enqueue(QueuedCommand("click", None, command))
    assert at_checkpoint.wait(1)
    pressed = True
    continue_command.set()
    assert not clicked.wait(0.05)
    assert manager.state == ExecutionState.PAUSED
    manager.resume()
    assert not clicked.wait(0.05)
    assert manager.state == ExecutionState.PAUSED
    pressed = False
    manager.resume()
    assert clicked.wait(1)
    manager.close()
