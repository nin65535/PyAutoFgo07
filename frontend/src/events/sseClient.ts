import { authenticatedFetch } from "../api/session";

export type ConnectionState = "connecting" | "active" | "inactive";

export type SseEvent = {
  event?: string;
  id?: string;
  data: unknown;
};

export type SseClientOptions = {
  url: string;
  onEvent: (event: SseEvent) => void;
  onStateChange: (state: ConnectionState) => void;
  fetchImpl?: typeof fetch;
  inactivityMs?: number;
  now?: () => number;
};

export class SseClient {
  private readonly abortController = new AbortController();
  private readonly fetchImpl: typeof fetch;
  private readonly inactivityMs: number;
  private readonly now: () => number;
  private lastReceivedAt = 0;
  private watchdog?: ReturnType<typeof setInterval>;
  private inactive = false;
  private readonly receivedEventKeys = new Set<string>();

  constructor(private readonly options: SseClientOptions) {
    this.fetchImpl = options.fetchImpl ?? authenticatedFetch;
    this.inactivityMs = options.inactivityMs ?? 10_000;
    this.now = options.now ?? Date.now;
  }

  async connect(): Promise<void> {
    this.options.onStateChange("connecting");
    this.lastReceivedAt = this.now();
    this.watchdog = setInterval(
      () => {
        if (this.now() - this.lastReceivedAt >= this.inactivityMs) {
          this.deactivate();
        }
      },
      Math.min(1_000, this.inactivityMs),
    );

    try {
      const response = await this.fetchImpl(this.options.url, {
        headers: { Accept: "text/event-stream" },
        signal: this.abortController.signal,
      });
      if (!response.ok || !response.body)
        throw new Error("SSE connection failed");
      this.options.onStateChange("active");
      await this.read(response.body);
      this.deactivate();
    } catch {
      this.deactivate();
    }
  }

  close(): void {
    this.deactivate();
  }

  private async read(stream: ReadableStream<Uint8Array>): Promise<void> {
    const reader = stream.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (!this.inactive) {
      const { done, value } = await reader.read();
      if (done) return;
      buffer += decoder
        .decode(value, { stream: true })
        .replaceAll("\r\n", "\n");
      let boundary = buffer.indexOf("\n\n");
      while (boundary >= 0) {
        const block = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        this.receive(block);
        boundary = buffer.indexOf("\n\n");
      }
    }
  }

  private receive(block: string): void {
    const fields = new Map<string, string>();
    for (const line of block.split("\n")) {
      const separator = line.indexOf(":");
      if (separator < 0) continue;
      fields.set(
        line.slice(0, separator),
        line.slice(separator + 1).trimStart(),
      );
    }
    const data = fields.get("data");
    if (data === undefined) return;
    this.lastReceivedAt = this.now();
    try {
      const parsed = JSON.parse(data) as {
        eventId?: unknown;
        sessionId?: unknown;
      };
      if (
        typeof parsed.eventId === "number" &&
        typeof parsed.sessionId === "string"
      ) {
        const key = `${parsed.sessionId}:${parsed.eventId}`;
        if (this.receivedEventKeys.has(key)) return;
        this.receivedEventKeys.add(key);
      }
      this.options.onEvent({
        event: fields.get("event"),
        id: fields.get("id"),
        data: parsed,
      });
    } catch {
      this.deactivate();
    }
  }

  private deactivate(): void {
    if (this.inactive) return;
    this.inactive = true;
    this.abortController.abort();
    if (this.watchdog !== undefined) clearInterval(this.watchdog);
    this.options.onStateChange("inactive");
  }
}
