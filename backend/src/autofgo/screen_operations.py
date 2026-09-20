from __future__ import annotations

import time
from dataclasses import dataclass
from threading import Event
from typing import Any, Protocol


class ScreenOperationError(Exception):
    """Base class for expected screen-operation failures."""


class OperationCancelledError(ScreenOperationError):
    pass


class OperationTimeoutError(ScreenOperationError):
    pass


class OutsideAllowedAreaError(ScreenOperationError):
    pass


class InvalidKeyError(ScreenOperationError):
    pass


@dataclass(frozen=True, slots=True)
class Point:
    x: int
    y: int


@dataclass(frozen=True, slots=True)
class ScreenRegion:
    """A half-open rectangle in the coordinate system exposed by pyautogui."""

    left: int
    top: int
    width: int
    height: int

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("width and height must be positive")

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height

    def contains_point(self, point: Point) -> bool:
        return self.left <= point.x < self.right and self.top <= point.y < self.bottom

    def contains_region(self, region: ScreenRegion) -> bool:
        return (
            self.left <= region.left
            and self.top <= region.top
            and region.right <= self.right
            and region.bottom <= self.bottom
        )

    def as_tuple(self) -> tuple[int, int, int, int]:
        return (self.left, self.top, self.width, self.height)


@dataclass(frozen=True, slots=True)
class ImageMatch:
    region: ScreenRegion

    @property
    def center(self) -> Point:
        return Point(
            self.region.left + self.region.width // 2,
            self.region.top + self.region.height // 2,
        )


class ScreenBackend(Protocol):
    def screenshot(self, region: tuple[int, int, int, int] | None = None) -> Any: ...

    def locate(self, needle: Any, haystack: Any) -> tuple[int, int, int, int] | None: ...

    def click(self, x: int, y: int) -> None: ...

    def press(self, key: str) -> None: ...


class PyAutoGuiBackend:
    """Small adapter that keeps pyautogui replaceable in automated tests."""

    def __init__(self) -> None:
        import pyautogui

        self._pyautogui = pyautogui
        self._pyautogui.FAILSAFE = True

    def screenshot(self, region: tuple[int, int, int, int] | None = None) -> Any:
        return self._pyautogui.screenshot(region=region)

    def locate(self, needle: Any, haystack: Any) -> tuple[int, int, int, int] | None:
        try:
            match = self._pyautogui.locate(needle, haystack)
        except self._pyautogui.ImageNotFoundException:
            return None
        if match is None:
            return None
        return (int(match.left), int(match.top), int(match.width), int(match.height))

    def click(self, x: int, y: int) -> None:
        self._pyautogui.click(x=x, y=y)

    def press(self, key: str) -> None:
        self._pyautogui.press(key)

    def primary_screen_size(self) -> tuple[int, int]:
        size = self._pyautogui.size()
        return (int(size.width), int(size.height))


ALLOWED_KEYS = frozenset({"esc", "enter", "space", "tab"})


class ScreenOperator:
    """Validated, cancellable screen primitives used by command execution."""

    def __init__(
        self,
        backend: ScreenBackend,
        allowed_area: ScreenRegion,
        *,
        default_timeout_seconds: float = 5.0,
        poll_interval_seconds: float = 0.1,
        clock: Any = time.monotonic,
    ) -> None:
        if default_timeout_seconds <= 0:
            raise ValueError("default timeout must be positive")
        if poll_interval_seconds <= 0:
            raise ValueError("poll interval must be positive")
        self._backend = backend
        self.allowed_area = allowed_area
        self.default_timeout_seconds = default_timeout_seconds
        self.poll_interval_seconds = poll_interval_seconds
        self._clock = clock

    def capture(self, region: ScreenRegion, *, cancel: Event | None = None) -> Any:
        self._validate_region(region)
        started_at = self._begin(cancel)
        image = self._backend.screenshot(region.as_tuple())
        self._finish(started_at, self.default_timeout_seconds, cancel)
        return image

    def crop(self, image: Any, region: ScreenRegion, *, cancel: Event | None = None) -> Any:
        started_at = self._begin(cancel)
        width, height = image.size
        image_area = ScreenRegion(0, 0, int(width), int(height))
        if not image_area.contains_region(region):
            raise OutsideAllowedAreaError("crop region is outside the source image")
        cropped = image.crop((region.left, region.top, region.right, region.bottom))
        self._finish(started_at, self.default_timeout_seconds, cancel)
        return cropped

    def locate(
        self,
        needle: Any,
        region: ScreenRegion,
        *,
        timeout_seconds: float | None = None,
        cancel: Event | None = None,
    ) -> ImageMatch | None:
        self._validate_region(region)
        timeout = self._timeout(timeout_seconds)
        started_at = self._begin(cancel)
        while True:
            haystack = self._backend.screenshot(region.as_tuple())
            found = self._backend.locate(needle, haystack)
            self._check_cancelled(cancel)
            if found is not None:
                relative = ScreenRegion(*found)
                haystack_area = ScreenRegion(0, 0, region.width, region.height)
                if not haystack_area.contains_region(relative):
                    raise OutsideAllowedAreaError("image matcher returned an invalid region")
                match = ImageMatch(
                    ScreenRegion(
                        region.left + relative.left,
                        region.top + relative.top,
                        relative.width,
                        relative.height,
                    )
                )
                self._finish(started_at, timeout, cancel)
                return match
            elapsed = self._clock() - started_at
            if elapsed >= timeout:
                return None
            self._wait(min(self.poll_interval_seconds, timeout - elapsed), cancel)

    def click(self, point: Point, *, cancel: Event | None = None) -> None:
        if not self.allowed_area.contains_point(point):
            raise OutsideAllowedAreaError("click point is outside the allowed screen area")
        started_at = self._begin(cancel)
        self._backend.click(point.x, point.y)
        self._finish(started_at, self.default_timeout_seconds, cancel)

    def press_key(self, key: str, *, cancel: Event | None = None) -> None:
        if key not in ALLOWED_KEYS:
            raise InvalidKeyError(f"key is not allowed: {key}")
        started_at = self._begin(cancel)
        self._backend.press(key)
        self._finish(started_at, self.default_timeout_seconds, cancel)

    def _validate_region(self, region: ScreenRegion) -> None:
        if not self.allowed_area.contains_region(region):
            raise OutsideAllowedAreaError("screen region is outside the allowed screen area")

    def _timeout(self, timeout_seconds: float | None) -> float:
        timeout = self.default_timeout_seconds if timeout_seconds is None else timeout_seconds
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        return timeout

    def _begin(self, cancel: Event | None) -> float:
        self._check_cancelled(cancel)
        return float(self._clock())

    def _finish(self, started_at: float, timeout: float, cancel: Event | None) -> None:
        self._check_cancelled(cancel)
        if self._clock() - started_at > timeout:
            raise OperationTimeoutError("screen operation exceeded its timeout")

    @staticmethod
    def _check_cancelled(cancel: Event | None) -> None:
        if cancel is not None and cancel.is_set():
            raise OperationCancelledError("screen operation was cancelled")

    def _wait(self, seconds: float, cancel: Event | None) -> None:
        if cancel is None:
            time.sleep(seconds)
        elif cancel.wait(seconds):
            raise OperationCancelledError("screen operation was cancelled")


def create_screen_operator() -> ScreenOperator:
    """Build the production operator from application settings."""
    from autofgo.config import get_settings

    settings = get_settings()
    backend = PyAutoGuiBackend()
    if settings.screen_width is None or settings.screen_height is None:
        width, height = backend.primary_screen_size()
        allowed_area = ScreenRegion(0, 0, width, height)
    else:
        allowed_area = ScreenRegion(
            settings.screen_left,
            settings.screen_top,
            settings.screen_width,
            settings.screen_height,
        )
    return ScreenOperator(
        backend,
        allowed_area,
        default_timeout_seconds=settings.operation_timeout_seconds,
        poll_interval_seconds=settings.image_poll_interval_seconds,
    )
