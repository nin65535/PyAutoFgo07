"""Launch the isolated card sampler API and its Chrome window."""

import asyncio
import logging
from pathlib import Path

import uvicorn

from autofgo.browser import ChromeLauncher
from autofgo.config import Settings
from autofgo.sampler_api import SamplerState, create_sampler_app


class SamplerChromeLauncher(ChromeLauncher):
    def __init__(self, settings: Settings, state: SamplerState) -> None:
        super().__init__(settings)
        self.state = state

    def arguments(self, executable: Path) -> list[str]:
        args = super().arguments(executable)
        args[-1] = (
            f"--app={self.settings.chrome_app_url}#"
            f"autofgoSession={self.state.security.session_id}&"
            f"autofgoToken={self.state.security.token}"
        )
        args.insert(-1, "--start-maximized")
        return args


async def run() -> None:
    settings = Settings(
        port=8010,
        chrome_profile_directory=Path(".autofgo/sampler-chrome-profile"),
        chrome_app_url="http://127.0.0.1:8010",
        chrome_window_width=1600,
        chrome_window_height=900,
    )
    state = SamplerState(Path("card-data/references/manifest.json"), settings.scenario_directory)
    server = uvicorn.Server(
        uvicorn.Config(
            create_sampler_app(state),
            host=settings.host,
            port=settings.port,
            log_level=settings.log_level.lower(),
        )
    )
    server_task = asyncio.create_task(server.serve())
    launcher = SamplerChromeLauncher(settings, state)
    try:
        while not server.started and not server_task.done():
            await asyncio.sleep(0.01)
        if server_task.done():
            await server_task
            raise RuntimeError("sampler API failed to start")
        process = launcher.launch()
        browser_task = asyncio.create_task(asyncio.to_thread(process.wait))
        disconnected_task = asyncio.create_task(state.disconnected.wait())
        while True:
            done, _ = await asyncio.wait(
                {server_task, browser_task, disconnected_task}, return_when=asyncio.FIRST_COMPLETED
            )
            if server_task in done or browser_task in done:
                break
            if disconnected_task in done:
                state.connected.clear()
                try:
                    await asyncio.wait_for(state.connected.wait(), timeout=5)
                except TimeoutError:
                    break
                disconnected_task = asyncio.create_task(state.disconnected.wait())
        state.closing = True
        async with state.saving:
            state.clear()
        server.should_exit = True
        launcher.terminate()
        await server_task
        browser_task.cancel()
        disconnected_task.cancel()
    finally:
        state.closing = True
        state.clear()
        state.security.invalidate()
        server.should_exit = True
        launcher.close()
        if not server_task.done():
            await server_task


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())


if __name__ == "__main__":
    main()
