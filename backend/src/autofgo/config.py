from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LOCAL_CHROME_AUTHORITY = re.compile(
    r"(?:localhost|127\.0\.0\.1|\[::1\])(?::[0-9]{1,5})?\Z", re.IGNORECASE
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AUTOFGO_", env_file=".env", extra="ignore")

    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"
    log_directory: Path = Path(".autofgo/logs")
    log_max_bytes: int = 2_000_000
    log_backup_count: int = 5
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
    static_directory: Path | None = None
    chrome_window_left: int = 0
    chrome_window_top: int = 0
    chrome_window_width: int = 200
    chrome_window_height: int = 1000

    @model_validator(mode="after")
    def validate_screen_settings(self) -> Settings:
        if self.host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("host must be a loopback address")
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
        if self.log_max_bytes <= 0 or self.log_backup_count < 0:
            raise ValueError("log rotation settings must be non-negative")
        if self.chrome_app_url != self.chrome_app_url.strip() or any(
            ord(character) < 32 or character == "\\" for character in self.chrome_app_url
        ):
            raise ValueError("Chrome app URL must use HTTP on localhost")
        try:
            parsed_url = urlsplit(self.chrome_app_url)
            port = parsed_url.port
        except ValueError as error:
            raise ValueError("Chrome app URL must use HTTP on localhost") from error
        if (
            parsed_url.scheme != "http"
            or not LOCAL_CHROME_AUTHORITY.fullmatch(parsed_url.netloc)
            or parsed_url.hostname not in {"127.0.0.1", "localhost", "::1"}
            or port == 0
        ):
            raise ValueError("Chrome app URL must use HTTP on localhost")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
