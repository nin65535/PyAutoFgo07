from __future__ import annotations

import asyncio
import json
from typing import Any

from autofgo.events import EventBroker
from autofgo.execution import ExecutionManager, QueuedCommand


class ConnectedRequest:
    async def is_disconnected(self) -> bool:
        return False


def parse_sse(message: str) -> tuple[dict[str, str], dict[str, Any]]:
    fields = dict(line.split(": ", 1) for line in message.strip().splitlines())
    return fields, json.loads(fields["data"])


def test_event_ids_increase_and_match_sse_payload() -> None:
    async def exercise() -> None:
        broker = EventBroker(heartbeat_seconds=1)
        stream = broker.stream(ConnectedRequest())  # type: ignore[arg-type]
        pending = asyncio.create_task(anext(stream))
        await asyncio.sleep(0)
        broker.publish("warning", {"code": "FIRST", "message": "first"})
        fields, payload = parse_sse(await pending)
        assert fields["id"] == "1"
        assert payload["eventId"] == 1
        assert payload["sessionId"] == broker.session_id
        await stream.aclose()

    asyncio.run(exercise())


def test_heartbeat_has_no_event_id() -> None:
    async def exercise() -> None:
        broker = EventBroker(heartbeat_seconds=0.001)
        stream = broker.stream(ConnectedRequest())  # type: ignore[arg-type]
        fields, payload = parse_sse(await anext(stream))
        assert fields["event"] == "heartbeat"
        assert "id" not in fields
        assert "eventId" not in payload
        await stream.aclose()

    asyncio.run(exercise())


def test_connection_observer_sees_establishment_and_disconnect() -> None:
    async def exercise() -> None:
        states: list[str] = []
        broker = EventBroker(heartbeat_seconds=1, connection_observer=states.append)
        stream = broker.stream(ConnectedRequest())  # type: ignore[arg-type]
        pending = asyncio.create_task(anext(stream))
        await asyncio.sleep(0)
        broker.publish("ready", {})
        await pending
        await stream.aclose()
        assert states == ["connected", "disconnected"]

    asyncio.run(exercise())


def test_execution_manager_emits_ordered_command_events() -> None:
    events: list[tuple[str, dict[str, Any], str | None]] = []
    manager = ExecutionManager(
        start_worker=False,
        event_sink=lambda event_type, data, command_id: events.append(
            (event_type, data, command_id)
        ),
    )
    manager.enqueue(QueuedCommand("command-1", "value", lambda value, control: None))

    assert [event[0] for event in events] == [
        "command.accepted",
        "execution.state_changed",
    ]
    assert events[0][2] == "command-1"
