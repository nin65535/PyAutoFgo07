"""Warn when the other local application is already serving requests."""

import logging
import socket

companion_was_running_at_start = False


def warn_if_companion_running(name: str, port: int) -> bool:
    global companion_was_running_at_start
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
            pass
    except OSError:
        companion_was_running_at_start = False
        return False
    companion_was_running_at_start = True
    logging.getLogger(__name__).warning(
        "%s is already running on 127.0.0.1:%s; reference changes become visible "
        "to the player at the next All/Wave start.",
        name,
        port,
    )
    return True
