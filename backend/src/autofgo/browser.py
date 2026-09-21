from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from contextlib import suppress
from pathlib import Path
from typing import Protocol

from autofgo.config import Settings


class BrowserLaunchError(RuntimeError):
    """Raised when the dedicated Chrome instance cannot be started safely."""


def chrome_candidates() -> tuple[Path, ...]:
    if sys.platform == "win32":
        roots = (
            os.environ.get("PROGRAMFILES"),
            os.environ.get("PROGRAMFILES(X86)"),
            os.environ.get("LOCALAPPDATA"),
        )
        return tuple(Path(root) / "Google/Chrome/Application/chrome.exe" for root in roots if root)
    if sys.platform == "darwin":
        return (Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),)
    return ()


PathPredicate = Callable[[Path], bool]


def find_chrome(
    configured_path: Path | None = None,
    *,
    is_file: PathPredicate = lambda path: path.is_file(),
) -> Path:
    if configured_path is not None:
        path = configured_path.expanduser().resolve()
        if not is_file(path):
            raise BrowserLaunchError(f"Configured Chrome executable does not exist: {path}")
        return path

    for candidate in chrome_candidates():
        if is_file(candidate):
            return candidate.resolve()

    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        discovered = shutil.which(name)
        if discovered:
            return Path(discovered).resolve()

    raise BrowserLaunchError(
        "Chrome executable was not found. Set AUTOFGO_CHROME_EXECUTABLE to its full path."
    )


def _process_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


class LockStore(Protocol):
    def try_create(self, owner: int) -> bool: ...

    def read_owner(self) -> int: ...

    def remove(self) -> None: ...


class FileLockStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def try_create(self, owner: int) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return False
        with os.fdopen(descriptor, "w", encoding="ascii") as lock_file:
            lock_file.write(str(owner))
        return True

    def read_owner(self) -> int:
        return int(self.path.read_text(encoding="ascii").strip())

    def remove(self) -> None:
        self.path.unlink(missing_ok=True)


class ProfileLock:
    def __init__(
        self,
        profile_directory: Path,
        *,
        store: LockStore | None = None,
        process_exists: Callable[[int], bool] = _process_exists,
        owner_pid: int | None = None,
    ) -> None:
        self.path = profile_directory / ".autofgo.lock"
        self._store = store or FileLockStore(self.path)
        self._process_exists = process_exists
        self._owner_pid = owner_pid if owner_pid is not None else os.getpid()
        self._held = False

    def acquire(self) -> None:
        for attempt in range(2):
            try:
                created = self._store.try_create(self._owner_pid)
            except OSError as error:
                raise BrowserLaunchError(
                    "Could not create the dedicated Chrome profile lock."
                ) from error
            if not created:
                try:
                    owner = self._store.read_owner()
                except (OSError, ValueError):
                    raise BrowserLaunchError(
                        "The dedicated Chrome profile lock is unreadable."
                    ) from None
                if self._process_exists(owner):
                    raise BrowserLaunchError(
                        f"The dedicated Chrome profile is already in use by process {owner}."
                    ) from None
                if attempt == 0:
                    with suppress(FileNotFoundError):
                        self._store.remove()
                    continue
                raise BrowserLaunchError(
                    "Could not acquire the dedicated Chrome profile lock."
                ) from None
            else:
                self._held = True
                return

    def release(self) -> None:
        if not self._held:
            return
        with suppress(FileNotFoundError):
            self._store.remove()
        self._held = False


ProcessFactory = Callable[[Sequence[str]], subprocess.Popen[bytes]]


class ChromeLauncher:
    def __init__(
        self,
        settings: Settings,
        process_factory: ProcessFactory = subprocess.Popen,
        *,
        executable_finder: Callable[[Path | None], Path] = find_chrome,
        profile_lock: ProfileLock | None = None,
    ) -> None:
        self.settings = settings
        self._process_factory = process_factory
        self._executable_finder = executable_finder
        self._profile_directory = settings.chrome_profile_directory.expanduser().resolve()
        self._lock = profile_lock or ProfileLock(self._profile_directory)
        self.process: subprocess.Popen[bytes] | None = None

    def arguments(self, executable: Path) -> list[str]:
        settings = self.settings
        return [
            str(executable),
            f"--user-data-dir={self._profile_directory}",
            "--no-first-run",
            "--no-default-browser-check",
            "--new-window",
            f"--window-position={settings.chrome_window_left},{settings.chrome_window_top}",
            f"--window-size={settings.chrome_window_width},{settings.chrome_window_height}",
            f"--app={settings.chrome_app_url}",
        ]

    def launch(self) -> subprocess.Popen[bytes]:
        executable = self._executable_finder(self.settings.chrome_executable)
        self._lock.acquire()
        try:
            self.process = self._process_factory(self.arguments(executable))
        except OSError as error:
            self._lock.release()
            raise BrowserLaunchError(f"Chrome failed to start: {error}") from error
        return self.process

    def close(self) -> None:
        self._lock.release()

    def terminate(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
