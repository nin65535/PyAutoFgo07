from __future__ import annotations

from pathlib import Path
from threading import Event
from typing import Any

import pytest
from PIL import Image

from autofgo.card_colors import CardColor
from autofgo.card_identity import CardIdentity
from autofgo.game_automation import (
    BattleScreenTimeoutError,
    CardRecognitionError,
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

    def capture(self, region: ScreenRegion, *, cancel: Event) -> Image.Image:
        return Image.new("RGB", (region.width, region.height))


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


def test_card_slots_recognize_and_select_before_card_clicks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import autofgo.game_automation as module

    names = ["A", "B", "C", "A", "B"]
    monkeypatch.setattr(
        module,
        "detect_card_colors",
        lambda _image, _viewport: tuple(
            CardColor(index, ScreenRegion(0, 0, 1, 1), color, {})
            for index, color in enumerate("BQAAB")
        ),
    )

    class Recognizer:
        def recognize(
            self, _image: Image.Image, _viewport: ScreenRegion
        ) -> tuple[CardIdentity, ...]:
            return tuple(
                CardIdentity(i, "recognized", "matched", name, 1, 20, ())
                for i, name in enumerate(names)
            )

    operator = FakeOperator()
    subject = automation(operator)
    subject._card_recognizer = Recognizer()  # type: ignore[assignment]
    reports = []
    subject.attack_with_slots(
        ["N0", "B1", "B0"],
        ["A", "B", "C"],
        FakeControl(),
        report=lambda *args: reports.append(args),
    )  # type: ignore[arg-type]
    assert reports[0][0] == "cards.selected"
    assert len(reports[0][1]["identities"]) == 5
    assert reports[0][1]["choices"][1] == {
        "slot": 2,
        "kind": "card",
        "position": 4,
        "matchedPreference": "B1",
    }
    assert operator.clicks == [
        Point(1890, 1090),
        Point(720, 350),
        Point(1820, 780),
        Point(300, 780),
    ]


def test_uncertain_card_identity_stops_before_card_click(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import autofgo.game_automation as module

    monkeypatch.setattr(
        module,
        "detect_card_colors",
        lambda *_args: tuple(CardColor(i, ScreenRegion(0, 0, 1, 1), "B", {}) for i in range(5)),
    )

    class Recognizer:
        def recognize(
            self, _image: Image.Image, _viewport: ScreenRegion
        ) -> tuple[CardIdentity, ...]:
            return tuple(
                CardIdentity(i, "unknown", "low_similarity", None, 80, 2, ()) for i in range(5)
            )

    operator = FakeOperator()
    subject = automation(operator)
    subject.failure_capture_dir = tmp_path / "card-failures"
    subject._card_recognizer = Recognizer()  # type: ignore[assignment]
    reports = []
    with pytest.raises(CardRecognitionError, match="low_similarity"):
        subject.attack_with_slots(
            ["B0", "", ""],
            ["A", "B", "C"],
            FakeControl(),
            report=lambda *args: reports.append(args),
        )  # type: ignore[arg-type]
    assert reports[0][0] == "cards.failed"
    assert reports[0][1]["identities"][0]["reason"] == "low_similarity"
    capture_path = Path(reports[0][1]["capturePath"])
    assert capture_path.parent == subject.failure_capture_dir
    with Image.open(capture_path) as saved:
        assert saved.size == (1962, 1115)
    assert operator.clicks == [Point(1890, 1090)]


def test_front_member_mismatch_stops_before_card_click(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import autofgo.game_automation as module

    monkeypatch.setattr(
        module,
        "detect_card_colors",
        lambda *_args: tuple(CardColor(i, ScreenRegion(0, 0, 1, 1), "B", {}) for i in range(5)),
    )

    class Recognizer:
        def recognize(
            self, _image: Image.Image, _viewport: ScreenRegion
        ) -> tuple[CardIdentity, ...]:
            return tuple(CardIdentity(i, "recognized", "matched", "X", 1, 20, ()) for i in range(5))

    operator = FakeOperator()
    subject = automation(operator)
    subject.failure_capture_dir = tmp_path / "card-failures"
    subject._card_recognizer = Recognizer()  # type: ignore[assignment]
    reports = []
    with pytest.raises(CardRecognitionError, match="do not match front members"):
        subject.attack_with_slots(
            ["B1", "", ""],
            ["A", "B", "C"],
            FakeControl(),
            report=lambda *args: reports.append(args),
        )  # type: ignore[arg-type]
    assert [event for event, _data in reports] == ["cards.failed"]
    assert reports[0][1]["identities"][0]["characterName"] == "X"
    assert reports[0][1]["frontMembers"] == ["A", "B", "C"]
    assert operator.clicks == [Point(1890, 1090)]


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
