from __future__ import annotations

import asyncio
from importlib import import_module
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

from autofgo.commands import CommandRegistry
from autofgo.execution import ExecutionManager
from autofgo.shutdown import EmergencyShutdown


def test_manual_shutdown_terminates_chrome_after_server_exit(monkeypatch) -> None:
    lifecycle = import_module("autofgo.__main__")
    registry = CommandRegistry(ExecutionManager(start_worker=False))
    release_inputs = Mock()
    process_exited = Event()

    class Server:
        started = True
        should_exit = False

        async def serve(self) -> None:
            while not self.should_exit:
                await asyncio.sleep(0.001)

    class Process:
        def wait(self) -> None:
            process_exited.wait(1)

    class Launcher:
        launched = False
        terminated = False

        def launch(self) -> Process:
            self.launched = True
            return Process()

        def terminate(self) -> None:
            self.terminated = True
            process_exited.set()

        def close(self) -> None:
            pass

    server = Server()
    launcher = Launcher()
    settings = SimpleNamespace(
        log_directory=Path("logs"),
        log_level="INFO",
        log_max_bytes=1000,
        log_backup_count=1,
        host="127.0.0.1",
        port=8000,
    )
    monkeypatch.setattr(lifecycle, "get_settings", lambda: settings)
    monkeypatch.setattr(lifecycle, "get_command_registry", lambda: registry)
    monkeypatch.setattr(lifecycle, "warn_if_companion_running", Mock())
    monkeypatch.setattr(lifecycle, "configure_logging", lambda *args, **kwargs: Path("logs"))
    monkeypatch.setattr(lifecycle.uvicorn, "Config", lambda *args, **kwargs: None)
    monkeypatch.setattr(lifecycle.uvicorn, "Server", lambda config: server)
    monkeypatch.setattr(lifecycle, "ChromeLauncher", lambda settings: launcher)
    monkeypatch.setattr(
        lifecycle, "GlobalSpacePause", lambda manager: SimpleNamespace(start=Mock(), close=Mock())
    )
    monkeypatch.setattr(lifecycle, "session_security", SimpleNamespace(invalidate=Mock()))
    monkeypatch.setattr(
        lifecycle,
        "EmergencyShutdown",
        lambda manager, request_exit: EmergencyShutdown(
            manager, request_exit, input_releaser=release_inputs
        ),
    )

    async def exercise() -> None:
        run_task = asyncio.create_task(lifecycle.run())

        async def wait_for_startup() -> None:
            while registry.emergency_shutdown is None or not launcher.launched:
                if run_task.done():
                    await run_task
                await asyncio.sleep(0.001)

        await asyncio.wait_for(wait_for_startup(), 2)
        registry.emergency_shutdown.trigger("emergency_stop")
        await asyncio.wait_for(run_task, 2)

    asyncio.run(exercise())
    assert server.should_exit is True
    assert launcher.terminated is True
    release_inputs.assert_called_once_with()
    assert registry.emergency_shutdown is None
