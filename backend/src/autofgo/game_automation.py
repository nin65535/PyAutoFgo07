from __future__ import annotations

import ctypes
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from PIL import Image

from autofgo.execution import ExecutionControl
from autofgo.screen_operations import Point, ScreenOperator, ScreenRegion, create_screen_operator


class GameAutomationError(Exception):
    """Base class for failures that make a game operation unsafe."""


class GameWindowNotFoundError(GameAutomationError):
    pass


class UnexpectedGameWindowSizeError(GameAutomationError):
    pass


class BattleScreenTimeoutError(GameAutomationError):
    pass


class WindowLocator(Protocol):
    def find(self, title: str) -> ScreenRegion: ...


class WindowsWindowLocator:
    """Locate an exact top-level window title without adding a pywin32 dependency."""

    def find(self, title: str) -> ScreenRegion:
        if sys.platform != "win32":
            raise GameWindowNotFoundError("game window lookup is supported only on Windows")

        user32 = ctypes.windll.user32
        # Match pyautogui's physical-pixel coordinate system even if the window
        # locator is used before pyautogui is initialized.
        user32.SetProcessDPIAware()
        found: list[ScreenRegion] = []

        class Rect(ctypes.Structure):
            _fields_ = [
                ("left", ctypes.c_long),
                ("top", ctypes.c_long),
                ("right", ctypes.c_long),
                ("bottom", ctypes.c_long),
            ]

        callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        @callback_type
        def visit(hwnd: int, _parameter: int) -> bool:
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            if buffer.value != title:
                return True
            rect = Rect()
            if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                found.append(
                    ScreenRegion(
                        int(rect.left),
                        int(rect.top),
                        int(rect.right - rect.left),
                        int(rect.bottom - rect.top),
                    )
                )
            return False

        user32.EnumWindows(visit, 0)
        if not found:
            raise GameWindowNotFoundError(f'game window was not found: "{title}"')
        return found[0]


@dataclass(frozen=True, slots=True)
class Element:
    left: int
    top: int
    width: int
    height: int

    @property
    def center(self) -> Point:
        return Point(self.left + self.width // 2, self.top + self.height // 2)


REFERENCE_WIDTH = 1962
REFERENCE_HEIGHT = 1115

ATTACK = Element(1780, 1030, 20, 20)
SKILLS = tuple(
    Element(left, 855, 100, 100) for left in (62, 193, 324, 539, 670, 801, 1016, 1147, 1278)
)
SKILL_TARGETS = tuple(
    Element(left, top, 100, 100) for top in (500, 600) for left in (450, 915, 1380)
)
SWAP_TARGETS = tuple(Element(left, 500, 100, 100) for left in (150, 450, 750, 1050, 1350, 1650))
SWAP_RUN = Element(910, 920, 100, 100)
ATTACK_CARDS = tuple(Element(left, 680, 100, 100) for left in (150, 530, 910, 1290, 1670))
NP_CARDS = tuple(Element(left, 250, 100, 100) for left in (570, 920, 1270))
MASTER_SKILL_CALL = Element(1740, 460, 100, 100)
MASTER_SKILLS = tuple(Element(left, 450, 100, 100) for left in (1310, 1445, 1580))


class GameAutomation:
    def __init__(
        self,
        operator: ScreenOperator,
        window_locator: WindowLocator,
        *,
        window_title: str = "LDPlayer",
        reference_size_tolerance: int = 4,
        battle_timeout_seconds: float = 50.0,
        sleep: Callable[[float], None] | None = None,
        attack_template: Image.Image | None = None,
    ) -> None:
        self.operator = operator
        self.window_locator = window_locator
        self.window_title = window_title
        self.reference_size_tolerance = reference_size_tolerance
        self.battle_timeout_seconds = battle_timeout_seconds
        self._sleep = sleep
        self._attack_template = attack_template

    def skill(self, skill_index: int, target_index: int | None, control: ExecutionControl) -> None:
        window = self._wait_for_battle(control)
        self._click(window, SKILLS[skill_index], control)
        if target_index is None:
            self._click(window, SKILLS[skill_index], control)
        else:
            self._wait(0.25, control)
            self._click(window, SKILL_TARGETS[target_index], control)
            self._click(window, SKILL_TARGETS[target_index], control)
        self._wait(1.0, control)

    def master_skill(
        self, skill_index: int, target_index: int | None, control: ExecutionControl
    ) -> None:
        window = self._wait_for_battle(control)
        self._click(window, MASTER_SKILL_CALL, control)
        self._wait(0.5, control)
        self._click(window, MASTER_SKILLS[skill_index], control)
        if target_index is None:
            self._click(window, MASTER_SKILLS[skill_index], control)
        else:
            self._wait(0.25, control)
            self._click(window, SKILL_TARGETS[target_index], control)
            self._click(window, SKILL_TARGETS[target_index], control)
        self._wait(1.0, control)

    def attack(self, noble_phantasm_indexes: list[int], control: ExecutionControl) -> None:
        window = self._wait_for_battle(control)
        self._click(window, ATTACK, control)
        self._wait(0.5, control)
        for index in noble_phantasm_indexes:
            self._click(window, NP_CARDS[index], control)
        for index in range(3 - len(noble_phantasm_indexes)):
            self._click(window, ATTACK_CARDS[index], control)

    def swap(self, front_index: int, back_index: int, control: ExecutionControl) -> None:
        window = self._wait_for_battle(control)
        self._click(window, MASTER_SKILL_CALL, control)
        self._wait(0.5, control)
        self._click(window, MASTER_SKILLS[2], control)
        self._wait(0.5, control)
        self._click(window, SWAP_TARGETS[front_index], control)
        self._click(window, SWAP_TARGETS[back_index], control)
        self._click(window, SWAP_RUN, control)
        self._wait(2.0, control)

    def _wait_for_battle(self, control: ExecutionControl) -> ScreenRegion:
        window = self._validated_window()
        template = self._get_attack_template()
        deadline = time.monotonic() + self.battle_timeout_seconds
        search = self._absolute_region(window, ATTACK, margin=True)
        while (remaining := deadline - time.monotonic()) > 0:
            control.checkpoint()
            match = self.operator.locate(
                template,
                search,
                timeout_seconds=min(self.operator.default_timeout_seconds, remaining),
                cancel=control.cancel_event,
            )
            if match is not None:
                return window
        raise BattleScreenTimeoutError("attack button was not detected before the timeout")

    def _validated_window(self) -> ScreenRegion:
        window = self.window_locator.find(self.window_title)
        if (
            abs(window.width - REFERENCE_WIDTH) > self.reference_size_tolerance
            or abs(window.height - REFERENCE_HEIGHT) > self.reference_size_tolerance
        ):
            raise UnexpectedGameWindowSizeError(
                f"expected about {REFERENCE_WIDTH}x{REFERENCE_HEIGHT}, "
                f"got {window.width}x{window.height}"
            )
        return window

    def _click(self, window: ScreenRegion, element: Element, control: ExecutionControl) -> None:
        control.checkpoint()
        point = element.center
        self.operator.click(
            Point(window.left + point.x, window.top + point.y),
            cancel=control.cancel_event,
        )

    def _absolute_region(
        self, window: ScreenRegion, element: Element, *, margin: bool = False
    ) -> ScreenRegion:
        if margin:
            return ScreenRegion(
                window.left + element.left - element.width // 2,
                window.top + element.top - element.height // 2,
                element.width * 2,
                element.height * 2,
            )
        return ScreenRegion(
            window.left + element.left,
            window.top + element.top,
            element.width,
            element.height,
        )

    def _wait(self, seconds: float, control: ExecutionControl) -> None:
        remaining = seconds
        while remaining > 0:
            control.checkpoint()
            interval = min(0.05, remaining)
            if self._sleep is None:
                if control.cancel_event.wait(interval):
                    control.checkpoint()
            else:
                self._sleep(interval)
            remaining -= interval

    def _get_attack_template(self) -> Image.Image:
        if self._attack_template is None:
            path = Path(__file__).parent / "assets" / "legacy" / "attack.png"
            with Image.open(path) as source:
                self._attack_template = source.copy()
        return self._attack_template


_game_automation: GameAutomation | None = None


def get_game_automation() -> GameAutomation:
    global _game_automation
    if _game_automation is None:
        _game_automation = GameAutomation(create_screen_operator(), WindowsWindowLocator())
    return _game_automation
