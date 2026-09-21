from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import Mock

import pytest

from autofgo.browser import BrowserLaunchError, ChromeLauncher, ProfileLock, find_chrome
from autofgo.config import Settings


def test_find_chrome_accepts_configured_executable(tmp_path: Path) -> None:
    executable = tmp_path / "chrome.exe"
    executable.touch()

    assert find_chrome(executable) == executable.resolve()


def test_find_chrome_rejects_missing_configured_executable(tmp_path: Path) -> None:
    with pytest.raises(BrowserLaunchError, match="does not exist"):
        find_chrome(tmp_path / "missing.exe")


def test_launcher_uses_dedicated_profile_and_window_settings(tmp_path: Path) -> None:
    executable = tmp_path / "chrome.exe"
    executable.touch()
    profile = tmp_path / "profile"
    process = Mock()
    process_factory = Mock(return_value=process)
    settings = Settings(
        chrome_executable=executable,
        chrome_profile_directory=profile,
        chrome_app_url="http://127.0.0.1:5173/app",
        chrome_window_left=-200,
        chrome_window_top=10,
        chrome_window_width=240,
        chrome_window_height=900,
    )
    launcher = ChromeLauncher(settings, process_factory=process_factory)

    try:
        assert launcher.launch() is process
        arguments = process_factory.call_args.args[0]
        assert f"--user-data-dir={profile.resolve()}" in arguments
        assert "--window-position=-200,10" in arguments
        assert "--window-size=240,900" in arguments
        assert "--app=http://127.0.0.1:5173/app" in arguments
        assert (profile / ".autofgo.lock").read_text(encoding="ascii") == str(os.getpid())
    finally:
        launcher.close()

    assert not (profile / ".autofgo.lock").exists()


def test_profile_lock_rejects_live_owner(tmp_path: Path) -> None:
    lock = ProfileLock(tmp_path)
    lock.path.parent.mkdir(parents=True, exist_ok=True)
    lock.path.write_text(str(os.getpid()), encoding="ascii")

    with pytest.raises(BrowserLaunchError, match="already in use"):
        lock.acquire()


def test_profile_lock_replaces_stale_owner(tmp_path: Path) -> None:
    lock = ProfileLock(tmp_path)
    lock.path.parent.mkdir(parents=True, exist_ok=True)
    lock.path.write_text("-1", encoding="ascii")

    lock.acquire()
    try:
        assert lock.path.read_text(encoding="ascii") == str(os.getpid())
    finally:
        lock.release()


def test_launcher_releases_lock_when_process_creation_fails(tmp_path: Path) -> None:
    executable = tmp_path / "chrome.exe"
    executable.touch()
    profile = tmp_path / "profile"
    process_factory = Mock(side_effect=OSError("denied"))
    launcher = ChromeLauncher(
        Settings(chrome_executable=executable, chrome_profile_directory=profile),
        process_factory=process_factory,
    )

    with pytest.raises(BrowserLaunchError, match="failed to start"):
        launcher.launch()

    assert not (profile / ".autofgo.lock").exists()


def test_launcher_terminates_running_process() -> None:
    process = Mock()
    process.poll.return_value = None
    launcher = ChromeLauncher(Settings())
    launcher.process = process

    launcher.terminate()

    process.terminate.assert_called_once_with()
