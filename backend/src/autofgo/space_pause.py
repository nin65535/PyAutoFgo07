from __future__ import annotations

import ctypes
import logging
import sys
from collections.abc import Callable
from threading import Event, Lock, Thread

from autofgo.execution import ExecutionManager, ExecutionState, InvalidExecutionStateError

logger = logging.getLogger(__name__)
VK_SPACE = 0x20


def windows_space_pressed() -> bool:
    """Read the system-wide key state without consuming the Space input."""
    return bool(ctypes.windll.user32.GetAsyncKeyState(VK_SPACE) & 0x8001)


class GlobalSpacePause:
    def __init__(
        self,
        manager: ExecutionManager,
        *,
        is_pressed: Callable[[], bool] = windows_space_pressed,
        interval_seconds: float = 0.05,
    ) -> None:
        self._manager = manager
        self._is_pressed = is_pressed
        self._interval_seconds = interval_seconds
        self._stop = Event()
        self._thread: Thread | None = None
        self._was_pressed = False
        self._poll_lock = Lock()

    def start(self) -> None:
        if sys.platform != "win32" or self._thread is not None:
            return
        self._manager.set_pause_input_check(self.poll_once)
        self._thread = Thread(target=self._run, name="global-space-pause", daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._manager.set_pause_input_check(None)
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1)

    def poll_once(self) -> None:
        with self._poll_lock:
            if self._manager.state != ExecutionState.RUNNING:
                self._was_pressed = False
                return
            pressed = self._is_pressed()
            if pressed and not self._was_pressed:
                try:
                    self._manager.pause()
                    logger.info(
                        "Execution paused by Space key",
                        extra={"event_type": "execution.space_pause"},
                    )
                    self._was_pressed = False
                    return
                except InvalidExecutionStateError:
                    pass  # State can change after it is read.
            self._was_pressed = pressed

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                running = self._manager.state == ExecutionState.RUNNING
                if running:
                    self.poll_once()
            except Exception:
                logger.exception("Global Space key monitor stopped")
                return
            interval = self._interval_seconds if running else 0.25
            self._stop.wait(interval)
