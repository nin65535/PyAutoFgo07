from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest

from autofgo.browser import BrowserLaunchError, ChromeLauncher, ProfileLock, find_chrome
from autofgo.config import Settings


class MemoryLockStore:
    def __init__(self, owner: int | None = None) -> None:
        self.owner = owner

    def try_create(self, owner: int) -> bool:
        if self.owner is not None:
            return False
        self.owner = owner
        return True

    def read_owner(self) -> int:
        if self.owner is None:
            raise FileNotFoundError
        return self.owner

    def remove(self) -> None:
        if self.owner is None:
            raise FileNotFoundError
        self.owner = None


def test_find_chrome_accepts_configured_executable_without_creating_a_file() -> None:
    executable = Path("C:/test/chrome.exe")
    resolved = executable.resolve()

    assert find_chrome(executable, is_file=lambda path: path == resolved) == resolved


def test_find_chrome_rejects_missing_configured_executable_without_filesystem_access() -> None:
    with pytest.raises(BrowserLaunchError, match="does not exist"):
        find_chrome(Path("C:/test/missing.exe"), is_file=lambda path: False)


def test_launcher_uses_dedicated_profile_and_window_settings() -> None:
    executable = Path("C:/test/chrome.exe").resolve()
    profile = Path("C:/test/profile")
    process = Mock()
    process_factory = Mock(return_value=process)
    lock = Mock(spec=ProfileLock)
    settings = Settings(
        chrome_executable=executable,
        chrome_profile_directory=profile,
        chrome_app_url="http://127.0.0.1:5173/app",
        chrome_window_left=-200,
        chrome_window_top=10,
        chrome_window_width=240,
        chrome_window_height=900,
    )
    launcher = ChromeLauncher(
        settings,
        process_factory=process_factory,
        executable_finder=Mock(return_value=executable),
        profile_lock=lock,
    )

    assert launcher.launch() is process
    arguments = process_factory.call_args.args[0]
    assert f"--user-data-dir={profile.resolve()}" in arguments
    assert "--window-position=-200,10" in arguments
    assert "--window-size=240,900" in arguments
    assert "--app=http://127.0.0.1:5173/app" in arguments
    lock.acquire.assert_called_once_with()

    launcher.close()
    lock.release.assert_called_once_with()


def test_profile_lock_rejects_live_owner_in_memory() -> None:
    store = MemoryLockStore(owner=123)
    lock = ProfileLock(
        Path("unused"),
        store=store,
        process_exists=lambda pid: pid == 123,
        owner_pid=456,
    )

    with pytest.raises(BrowserLaunchError, match="already in use"):
        lock.acquire()


def test_profile_lock_replaces_stale_owner_in_memory() -> None:
    store = MemoryLockStore(owner=123)
    lock = ProfileLock(
        Path("unused"),
        store=store,
        process_exists=lambda pid: False,
        owner_pid=456,
    )

    lock.acquire()
    assert store.owner == 456
    lock.release()
    assert store.owner is None


def test_launcher_releases_lock_when_process_creation_fails() -> None:
    executable = Path("C:/test/chrome.exe").resolve()
    lock = Mock(spec=ProfileLock)
    launcher = ChromeLauncher(
        Settings(chrome_executable=executable, chrome_profile_directory=Path("C:/test/profile")),
        process_factory=Mock(side_effect=OSError("denied")),
        executable_finder=Mock(return_value=executable),
        profile_lock=lock,
    )

    with pytest.raises(BrowserLaunchError, match="failed to start"):
        launcher.launch()

    lock.release.assert_called_once_with()


def test_launcher_terminates_running_process() -> None:
    process = Mock()
    process.poll.return_value = None
    launcher = ChromeLauncher(Settings())
    launcher.process = process

    launcher.terminate()

    process.terminate.assert_called_once_with()


@pytest.mark.integration
def test_profile_lock_uses_the_real_filesystem(tmp_path: Path) -> None:
    lock = ProfileLock(tmp_path, owner_pid=456)

    lock.acquire()
    assert lock.path.read_text(encoding="ascii") == "456"
    lock.release()
    assert not lock.path.exists()
