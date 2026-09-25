from __future__ import annotations

import asyncio
import logging

import uvicorn

from autofgo.browser import BrowserLaunchError, ChromeLauncher
from autofgo.commands import get_command_registry
from autofgo.config import get_settings
from autofgo.events import event_broker
from autofgo.security import session_security
from autofgo.shutdown import EmergencyShutdown


async def run() -> None:
    settings = get_settings()
    server = uvicorn.Server(
        uvicorn.Config(
            "autofgo.main:app",
            host=settings.host,
            port=settings.port,
            log_level=settings.log_level.lower(),
        )
    )
    server_task = asyncio.create_task(server.serve())
    launcher = ChromeLauncher(settings)
    connection_lost = asyncio.Event()
    was_connected = False

    def observe_connection(state: str) -> None:
        nonlocal was_connected
        if state == "connected":
            was_connected = True
        elif state == "disconnected" and was_connected:
            connection_lost.set()

    shutdown = EmergencyShutdown(
        get_command_registry().manager,
        lambda: setattr(server, "should_exit", True),
    )
    event_broker.set_connection_observer(observe_connection)

    try:
        while not server.started and not server_task.done():
            await asyncio.sleep(0.01)
        if server_task.done():
            await server_task
            return
        process = launcher.launch()
        process_task = asyncio.create_task(asyncio.to_thread(process.wait))
        disconnect_task = asyncio.create_task(connection_lost.wait())
        done, _ = await asyncio.wait(
            {server_task, process_task, disconnect_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if process_task in done:
            shutdown.trigger("chrome_process_exited")
        elif disconnect_task in done:
            shutdown.trigger("sse_disconnected")
            launcher.terminate()
        elif server_task in done and not shutdown.triggered:
            shutdown.trigger("backend_server_stopped")
            launcher.terminate()
        await server_task
        for task in (process_task, disconnect_task):
            if not task.done():
                task.cancel()
    except BrowserLaunchError:
        logging.getLogger(__name__).exception("Dedicated Chrome startup failed")
        server.should_exit = True
        await server_task
        raise
    finally:
        session_security.invalidate()
        event_broker.set_connection_observer(None)
        launcher.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
