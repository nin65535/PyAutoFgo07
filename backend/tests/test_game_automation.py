from __future__ import annotations

from threading import Event
from typing import Any

import pytest

from autofgo.game_automation import (
    BattleScreenTimeoutError,
    GameAutomation,
    UnexpectedGameWindowSizeError,
)
from autofgo.screen_operations import OperationTimeoutError, Point, ScreenRegion


class FakeControl:
    def __init__(self) -> None:
        self.cancel_event = Event()
        self.checkpoints = 0

    def checkpoint(self) -> None:
        self.checkpoints += 1


class FakeWindowLocator:
    def __init__(self, region: ScreenRegion | None = None) -> None:
        self.region = region or ScreenRegion(100, 50, 1962, 1115)
        self.titles: list[str] = []

    def find(self, title: str) -> ScreenRegion:
        self.titles.append(title)
        return self.region


class FakeOperator:
    poll_interval_seconds = 0.1
    default_timeout_seconds = 5.0

    def __init__(self, matches: list[object | None] | None = None) -> None:
        self.matches = matches or [object()]
        self.searches: list[ScreenRegion] = []
        self.clicks: list[Point] = []

    def locate(
        self,
        needle: Any,
        region: ScreenRegion,
        *,
        timeout_seconds: float,
        cancel: Event,
    ) -> object | None:
        self.searches.append(region)
        return self.matches.pop(0) if self.matches else None

    def click(self, point: Point, *, cancel: Event) -> None:
        self.clicks.append(point)


def automation(operator: FakeOperator, locator: FakeWindowLocator | None = None) -> GameAutomation:
    return GameAutomation(
        operator,  # type: ignore[arg-type]
        locator or FakeWindowLocator(),
        sleep=lambda _seconds: None,
        attack_template=object(),  # type: ignore[arg-type]
    )


def test_skill_waits_for_attack_and_clicks_legacy_relative_coordinates() -> None:
    operator = FakeOperator()
    control = FakeControl()

    automation(operator).skill(1, 2, control)  # type: ignore[arg-type]

    assert operator.searches == [ScreenRegion(1870, 1070, 40, 40)]
    assert operator.clicks == [Point(343, 955), Point(1530, 600), Point(1530, 600)]
    assert control.checkpoints > 0


def test_attack_selects_noble_phantasms_then_fills_three_cards() -> None:
    operator = FakeOperator()

    automation(operator).attack([2], FakeControl())  # type: ignore[arg-type]

    assert operator.clicks == [
        Point(1890, 1090),
        Point(1420, 350),
        Point(300, 780),
        Point(680, 780),
    ]


def test_swap_preserves_legacy_click_order() -> None:
    operator = FakeOperator()

    automation(operator).swap(1, 4, FakeControl())  # type: ignore[arg-type]

    assert operator.clicks == [
        Point(1890, 560),
        Point(1730, 550),
        Point(600, 600),
        Point(1500, 600),
        Point(1060, 1020),
    ]


def test_refuses_to_click_when_window_size_differs_from_reference() -> None:
    operator = FakeOperator()
    locator = FakeWindowLocator(ScreenRegion(0, 0, 1280, 720))

    with pytest.raises(UnexpectedGameWindowSizeError):
        automation(operator, locator).attack([], FakeControl())  # type: ignore[arg-type]

    assert operator.clicks == []


def test_times_out_without_clicking_when_battle_screen_is_not_detected() -> None:
    operator = FakeOperator([None, None])
    subject = automation(operator)
    subject.battle_timeout_seconds = 0.2

    with pytest.raises(BattleScreenTimeoutError):
        subject.attack([], FakeControl())  # type: ignore[arg-type]

    assert operator.clicks == []


def test_battle_detection_allows_a_capture_longer_than_poll_interval() -> None:
    class SlowCaptureOperator(FakeOperator):
        def locate(
            self,
            needle: Any,
            region: ScreenRegion,
            *,
            timeout_seconds: float,
            cancel: Event,
        ) -> object | None:
            if timeout_seconds < 0.5:
                raise OperationTimeoutError("capture needs more than 0.1 seconds")
            return super().locate(needle, region, timeout_seconds=timeout_seconds, cancel=cancel)

    operator = SlowCaptureOperator()

    automation(operator).attack([], FakeControl())  # type: ignore[arg-type]

    assert len(operator.clicks) == 4
