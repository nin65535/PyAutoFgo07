from __future__ import annotations

from threading import Event
from typing import Any

import pytest

from autofgo.screen_operations import (
    InvalidKeyError,
    OperationCancelledError,
    OperationTimeoutError,
    OutsideAllowedAreaError,
    Point,
    ScreenOperator,
    ScreenRegion,
)


class FakeImage:
    def __init__(self, size: tuple[int, int]) -> None:
        self.size = size
        self.crops: list[tuple[int, int, int, int]] = []

    def crop(self, box: tuple[int, int, int, int]) -> FakeImage:
        self.crops.append(box)
        return FakeImage((box[2] - box[0], box[3] - box[1]))


class FakeBackend:
    def __init__(self) -> None:
        self.screenshots: list[tuple[int, int, int, int] | None] = []
        self.clicks: list[tuple[int, int]] = []
        self.keys: list[str] = []
        self.matches: list[tuple[int, int, int, int] | None] = []
        self.image = FakeImage((100, 100))

    def screenshot(self, region: tuple[int, int, int, int] | None = None) -> FakeImage:
        self.screenshots.append(region)
        return self.image

    def locate(self, needle: Any, haystack: Any) -> tuple[int, int, int, int] | None:
        return self.matches.pop(0) if self.matches else None

    def click(self, x: int, y: int) -> None:
        self.clicks.append((x, y))

    def press(self, key: str) -> None:
        self.keys.append(key)


@pytest.fixture
def backend() -> FakeBackend:
    return FakeBackend()


@pytest.fixture
def operator(backend: FakeBackend) -> ScreenOperator:
    return ScreenOperator(backend, ScreenRegion(-100, 20, 300, 200), poll_interval_seconds=0.001)


def test_capture_accepts_negative_monitor_coordinates(
    operator: ScreenOperator, backend: FakeBackend
) -> None:
    image = operator.capture(ScreenRegion(-50, 30, 100, 80))

    assert image is backend.image
    assert backend.screenshots == [(-50, 30, 100, 80)]


def test_capture_rejects_region_outside_allowed_area(operator: ScreenOperator) -> None:
    with pytest.raises(OutsideAllowedAreaError):
        operator.capture(ScreenRegion(150, 30, 100, 80))


def test_crop_uses_image_relative_coordinates(operator: ScreenOperator) -> None:
    source = FakeImage((80, 60))

    result = operator.crop(source, ScreenRegion(5, 10, 20, 30))

    assert result.size == (20, 30)
    assert source.crops == [(5, 10, 25, 40)]


def test_crop_rejects_region_outside_source_image(operator: ScreenOperator) -> None:
    with pytest.raises(OutsideAllowedAreaError):
        operator.crop(FakeImage((20, 20)), ScreenRegion(10, 10, 11, 10))


def test_locate_returns_absolute_match_coordinates(
    operator: ScreenOperator, backend: FakeBackend
) -> None:
    backend.matches = [(4, 6, 10, 8)]

    match = operator.locate(object(), ScreenRegion(-50, 30, 100, 80), timeout_seconds=0.1)

    assert match is not None
    assert match.region == ScreenRegion(-46, 36, 10, 8)
    assert match.center == Point(-41, 40)


def test_locate_returns_none_at_timeout(backend: FakeBackend) -> None:
    times = iter([0.0, 0.1])
    operator = ScreenOperator(
        backend,
        ScreenRegion(0, 0, 100, 100),
        poll_interval_seconds=0.01,
        clock=lambda: next(times),
    )

    assert operator.locate(object(), ScreenRegion(0, 0, 20, 20), timeout_seconds=0.1) is None
    assert len(backend.screenshots) == 1


def test_click_validates_point_and_checks_cancellation(
    operator: ScreenOperator, backend: FakeBackend
) -> None:
    operator.click(Point(-100, 20))
    assert backend.clicks == [(-100, 20)]

    with pytest.raises(OutsideAllowedAreaError):
        operator.click(Point(200, 20))

    cancelled = Event()
    cancelled.set()
    with pytest.raises(OperationCancelledError):
        operator.click(Point(0, 30), cancel=cancelled)
    assert backend.clicks == [(-100, 20)]


def test_key_input_is_restricted_to_allowlist(
    operator: ScreenOperator, backend: FakeBackend
) -> None:
    operator.press_key("esc")
    assert backend.keys == ["esc"]

    with pytest.raises(InvalidKeyError):
        operator.press_key("a")


def test_completed_primitive_reports_timeout(backend: FakeBackend) -> None:
    times = iter([0.0, 6.0])
    operator = ScreenOperator(
        backend,
        ScreenRegion(0, 0, 100, 100),
        default_timeout_seconds=5.0,
        clock=lambda: next(times),
    )

    with pytest.raises(OperationTimeoutError):
        operator.click(Point(10, 10))
