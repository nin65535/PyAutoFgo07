import sys
from types import SimpleNamespace
from unittest.mock import Mock

from autofgo.execution import ExecutionManager, ExecutionState
from autofgo.shutdown import EmergencyShutdown, release_inputs


def test_release_inputs_does_not_send_right_button_up(monkeypatch) -> None:
    mouse_up = Mock()
    key_up = Mock()
    monkeypatch.setitem(sys.modules, "pyautogui", SimpleNamespace(mouseUp=mouse_up, keyUp=key_up))

    release_inputs()

    mouse_up.assert_called_once_with(button="left")
    assert key_up.call_count == 4


def test_shutdown_cancels_work_releases_inputs_and_requests_server_exit() -> None:
    manager = ExecutionManager(start_worker=False)
    release_inputs = Mock()
    request_exit = Mock()
    shutdown = EmergencyShutdown(
        manager,
        request_exit,
        input_releaser=release_inputs,
    )

    assert shutdown.trigger("chrome_process_exited") is True
    assert manager.state == ExecutionState.EMERGENCY_STOPPING
    assert manager.snapshot()["acceptingCommands"] is False
    release_inputs.assert_called_once_with()
    request_exit.assert_called_once_with()


def test_shutdown_is_idempotent_even_when_input_release_fails() -> None:
    manager = ExecutionManager(start_worker=False)
    request_exit = Mock()
    shutdown = EmergencyShutdown(
        manager,
        request_exit,
        input_releaser=Mock(side_effect=RuntimeError("release failed")),
    )

    assert shutdown.trigger("sse_disconnected") is True
    assert shutdown.trigger("chrome_process_exited") is False
    request_exit.assert_called_once_with()
