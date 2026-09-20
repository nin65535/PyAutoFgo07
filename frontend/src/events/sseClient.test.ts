import { afterEach, describe, expect, it, vi } from "vitest";
import { SseClient, type ConnectionState } from "./sseClient";

afterEach(() => vi.useRealTimers());

function streamOf(...chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
}

describe("SseClient", () => {
  it("parses normal events and heartbeat messages", async () => {
    const events: unknown[] = [];
    const states: ConnectionState[] = [];
    const fetchImpl = vi.fn(async () =>
      Promise.resolve(
        new Response(
          streamOf(
            'event: heartbeat\ndata: {"type":"heartbeat"}\n\n',
            'id: 1\nevent: command.accepted\ndata: {"eventId":1}\n\n',
          ),
          { status: 200 },
        ),
      ),
    ) as unknown as typeof fetch;
    const client = new SseClient({
      url: "/api/events",
      fetchImpl,
      onEvent: (event) => events.push(event),
      onStateChange: (state) => states.push(state),
    });

    await client.connect();

    expect(events).toHaveLength(2);
    expect(events[1]).toMatchObject({ event: "command.accepted", id: "1" });
    expect(states).toEqual(["connecting", "active", "inactive"]);
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("ignores a duplicate event in the same session", async () => {
    const events: unknown[] = [];
    const payload = '{"eventId":7,"sessionId":"session-1"}';
    const fetchImpl = vi.fn(async () =>
      Promise.resolve(
        new Response(
          streamOf(
            `id: 7\nevent: command.completed\ndata: ${payload}\n\n`,
            `id: 7\nevent: command.completed\ndata: ${payload}\n\n`,
          ),
          { status: 200 },
        ),
      ),
    ) as unknown as typeof fetch;
    const client = new SseClient({
      url: "/api/events",
      fetchImpl,
      onEvent: (event) => events.push(event),
      onStateChange: () => undefined,
    });

    await client.connect();

    expect(events).toHaveLength(1);
  });

  it("becomes inactive after ten seconds without a message", async () => {
    vi.useFakeTimers();
    const states: ConnectionState[] = [];
    const body = new ReadableStream<Uint8Array>({});
    const fetchImpl = vi.fn(
      async () => new Response(body, { status: 200 }),
    ) as unknown as typeof fetch;
    const client = new SseClient({
      url: "/api/events",
      fetchImpl,
      now: () => Date.now(),
      onEvent: () => undefined,
      onStateChange: (state) => states.push(state),
    });

    void client.connect();
    await vi.advanceTimersByTimeAsync(10_000);

    expect(states).toContain("inactive");
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });
});
