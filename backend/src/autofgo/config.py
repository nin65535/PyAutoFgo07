from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AUTOFGO_", env_file=".env", extra="ignore")

    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"
    scenario_directory: Path = Path("scenarios")
    screen_left: int = 0
    screen_top: int = 0
    screen_width: int | None = None
    screen_height: int | None = None
    operation_timeout_seconds: float = 5.0
    image_poll_interval_seconds: float = 0.1
    chrome_executable: Path | None = None
    chrome_profile_directory: Path = Path(".autofgo/chrome-profile")
    chrome_app_url: str = "http://127.0.0.1:5173"
    chrome_window_left: int = 0
    chrome_window_top: int = 0
    chrome_window_width: int = 200
    chrome_window_height: int = 1000

    @model_validator(mode="after")
    def validate_screen_settings(self) -> Settings:
        if (self.screen_width is None) != (self.screen_height is None):
            raise ValueError("screen width and height must both be set or both be omitted")
        if self.screen_width is not None and self.screen_width <= 0:
            raise ValueError("screen width must be positive")
        if self.screen_height is not None and self.screen_height <= 0:
            raise ValueError("screen height must be positive")
        if self.operation_timeout_seconds <= 0 or self.image_poll_interval_seconds <= 0:
            raise ValueError("screen operation timings must be positive")
        if self.chrome_window_width <= 0 or self.chrome_window_height <= 0:
            raise ValueError("Chrome window width and height must be positive")
        if not self.chrome_app_url.startswith(("http://127.0.0.1", "http://localhost")):
            raise ValueError("Chrome app URL must use HTTP on localhost")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
