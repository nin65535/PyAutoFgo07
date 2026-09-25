from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from threading import Lock
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from autofgo.security import session_security


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    eventId: int
    sessionId: str
    type: str
    occurredAt: str
    data: dict[str, Any]
    commandId: str | None = None

    def payload(self) -> dict[str, Any]:
        value = asdict(self)
        if self.commandId is None:
            del value["commandId"]
        return value


class EventBroker:
    """Process-local fan-out for live events. Events are deliberately not replayed."""

    def __init__(
        self,
        *,
        heartbeat_seconds: float = 3.0,
        connection_observer: Callable[[str], None] | None = None,
    ) -> None:
        self.session_id = session_security.session_id
        self.heartbeat_seconds = heartbeat_seconds
        self._next_id = 1
        self._lock = Lock()
        self._subscribers: set[tuple[asyncio.AbstractEventLoop, asyncio.Queue[EventEnvelope]]] = (
            set()
        )
        self._connection_observer = connection_observer

    def set_connection_observer(self, observer: Callable[[str], None] | None) -> None:
        with self._lock:
            self._connection_observer = observer

    def _observe_connection(self, state: str) -> None:
        with self._lock:
            observer = self._connection_observer
        if observer is not None:
            observer(state)

    def publish(
        self, event_type: str, data: dict[str, Any], *, command_id: str | None = None
    ) -> EventEnvelope:
        with self._lock:
            event = EventEnvelope(
                eventId=self._next_id,
                sessionId=self.session_id,
                type=event_type,
                occurredAt=_utc_now(),
                commandId=command_id,
                data=data,
            )
            self._next_id += 1
            subscribers = tuple(self._subscribers)
        for loop, queue in subscribers:
            loop.call_soon_threadsafe(queue.put_nowait, event)
        return event

    async def stream(self, request: Request) -> AsyncIterator[str]:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[EventEnvelope] = asyncio.Queue()
        subscriber = (loop, queue)
        with self._lock:
            self._subscribers.add(subscriber)
        self._observe_connection("connected")
        try:
            while not await request.is_disconnected():
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=self.heartbeat_seconds)
                except TimeoutError:
                    heartbeat = {
                        "type": "heartbeat",
                        "sessionId": self.session_id,
                        "sentAt": _utc_now(),
                    }
                    heartbeat_json = json.dumps(heartbeat, separators=(",", ":"))
                    yield f"event: heartbeat\ndata: {heartbeat_json}\n\n"
                else:
                    payload = json.dumps(event.payload(), separators=(",", ":"), ensure_ascii=False)
                    yield f"id: {event.eventId}\nevent: {event.type}\ndata: {payload}\n\n"
        finally:
            with self._lock:
                self._subscribers.discard(subscriber)
            self._observe_connection("disconnected")


event_broker = EventBroker()
router = APIRouter(tags=["events"])


@router.get("/api/events")
async def events(request: Request) -> StreamingResponse:
    return StreamingResponse(
        event_broker.stream(request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
