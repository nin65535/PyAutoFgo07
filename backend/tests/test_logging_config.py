from __future__ import annotations

import json
import logging
from pathlib import Path

from autofgo.logging_config import configure_logging

LOG_DIRECTORY = Path(__file__).parent


def _remove_test_logs() -> None:
    root = logging.getLogger()
    for handler in tuple(root.handlers):
        if Path(getattr(handler, "baseFilename", "")).name.startswith("autofgo.log"):
            root.removeHandler(handler)
            handler.close()
    for name in ("autofgo.log", "autofgo.log.1"):
        (LOG_DIRECTORY / name).unlink(missing_ok=True)


def test_structured_log_contains_context_without_unapproved_fields() -> None:
    _remove_test_logs()
    path = configure_logging(LOG_DIRECTORY, max_bytes=10_000, backup_count=1)
    logging.getLogger("test").info(
        "accepted",
        extra={"event_type": "command.accepted", "command_id": "cmd-1", "token": "secret"},
    )
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["severity"] == "INFO"
    assert record["eventType"] == "command.accepted"
    assert record["commandId"] == "cmd-1"
    assert "secret" not in path.read_text(encoding="utf-8")
    _remove_test_logs()


def test_log_rotates_at_configured_size() -> None:
    _remove_test_logs()
    path = configure_logging(LOG_DIRECTORY, max_bytes=120, backup_count=1)
    logger = logging.getLogger("rotation")
    logger.info("first-message", extra={"event_type": "test"})
    logger.info("second-message", extra={"event_type": "test"})
    assert path.exists()
    assert (LOG_DIRECTORY / "autofgo.log.1").exists()
    _remove_test_logs()
