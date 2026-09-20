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
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
