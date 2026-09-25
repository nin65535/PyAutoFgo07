import type { ConnectionState, SseEvent } from "./sseClient";

export type LogSeverity = "info" | "warning" | "error";
export type LogEntry = {
  id: string;
  occurredAt: string;
  severity: LogSeverity;
  eventType: string;
  message: string;
  commandId?: string;
  detail?: unknown;
};

const messages: Record<string, string> = {
  "command.accepted": "指令を受け付けました。",
  "command.started": "指令の実行を開始しました。",
  "command.completed": "指令を完了しました。",
  "command.failed": "指令の実行に失敗しました。",
  "command.cancelled": "指令を破棄しました。",
  "execution.state_changed": "実行状態が変わりました。",
};

export function entryFromSse(event: SseEvent): LogEntry | undefined {
  if (!event.event || event.event === "heartbeat") return undefined;
  const envelope =
    typeof event.data === "object" && event.data !== null
      ? (event.data as Record<string, unknown>)
      : undefined;
  const commandId = envelope?.commandId;
  const occurredAt = envelope?.occurredAt;
  return {
    id: `sse-${String(envelope?.eventId ?? event.id ?? Date.now())}`,
    occurredAt:
      typeof occurredAt === "string" ? occurredAt : new Date().toISOString(),
    severity: event.event === "command.failed" ? "error" : "info",
    eventType: event.event,
    message: messages[event.event] ?? "バックエンドから通知を受信しました。",
    commandId: typeof commandId === "string" ? commandId : undefined,
    detail: envelope?.data,
  };
}

export function connectionEntry(state: ConnectionState): LogEntry {
  const descriptions = {
    connecting: "バックエンドへ接続しています。",
    active: "バックエンドへ接続しました。",
    inactive: "バックエンドとの接続が切れました。",
  };
  return {
    id: `connection-${state}-${Date.now()}`,
    occurredAt: new Date().toISOString(),
    severity: state === "inactive" ? "error" : "info",
    eventType: `connection.${state}`,
    message: descriptions[state],
  };
}

export function localEntry(
  eventType: string,
  message: string,
  severity: LogSeverity = "info",
  detail?: unknown,
): LogEntry {
  const occurredAt = new Date().toISOString();
  return {
    id: `${eventType}-${occurredAt}-${Math.random()}`,
    occurredAt,
    severity,
    eventType,
    message,
    detail,
  };
}
