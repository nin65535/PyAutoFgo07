from __future__ import annotations

import asyncio
import logging

import uvicorn

from autofgo.browser import BrowserLaunchError, ChromeLauncher
from autofgo.config import get_settings


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

    try:
        while not server.started and not server_task.done():
            await asyncio.sleep(0.01)
        if server_task.done():
            await server_task
            return
        launcher.launch()
        await server_task
    except BrowserLaunchError:
        logging.getLogger(__name__).exception("Dedicated Chrome startup failed")
        server.should_exit = True
        await server_task
        raise
    finally:
        launcher.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
