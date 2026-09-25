from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any


class JsonLogFormatter(logging.Formatter):
    """Format a small, explicitly allow-listed JSON log record."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "severity": record.levelname,
            "eventType": getattr(record, "event_type", record.name),
            "message": record.getMessage(),
        }
        command_id = getattr(record, "command_id", None)
        if command_id is not None:
            payload["commandId"] = command_id
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging(
    directory: Path,
    *,
    level: str = "INFO",
    max_bytes: int = 2_000_000,
    backup_count: int = 5,
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    log_path = directory / "autofgo.log"
    handler = RotatingFileHandler(
        log_path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
    )
    handler.setFormatter(JsonLogFormatter())
    root = logging.getLogger()
    root.setLevel(level.upper())
    for existing in tuple(root.handlers):
        root.removeHandler(existing)
        existing.close()
    root.addHandler(handler)
    return log_path
