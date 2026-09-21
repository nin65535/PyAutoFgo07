from __future__ import annotations

import logging
from collections.abc import Callable
from threading import Lock

from autofgo.execution import ExecutionManager


def release_inputs() -> None:
    """Best-effort release of inputs that may remain held after an interrupted action."""
    import pyautogui

    for button in ("left", "middle", "right"):
        pyautogui.mouseUp(button=button)
    for key in ("shift", "ctrl", "alt", "win"):
        pyautogui.keyUp(key)


class EmergencyShutdown:
    """Idempotent safety actions shared by every fatal lifecycle path."""

    def __init__(
        self,
        manager: ExecutionManager,
        request_server_exit: Callable[[], None],
        *,
        input_releaser: Callable[[], None] = release_inputs,
        logger: logging.Logger | None = None,
    ) -> None:
        self._manager = manager
        self._request_server_exit = request_server_exit
        self._input_releaser = input_releaser
        self._logger = logger or logging.getLogger(__name__)
        self._lock = Lock()
        self._triggered = False

    @property
    def triggered(self) -> bool:
        with self._lock:
            return self._triggered

    def trigger(self, reason: str) -> bool:
        with self._lock:
            if self._triggered:
                return False
            self._triggered = True

        self._logger.error("Emergency shutdown triggered: %s", reason)
        self._manager.emergency_stop(reason)
        try:
            self._input_releaser()
        except Exception:
            self._logger.exception("Failed to release held input during emergency shutdown")
        self._request_server_exit()
        return True
