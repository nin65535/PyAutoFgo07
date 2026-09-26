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

function cardMessage(eventType: string, data: unknown): string | undefined {
  if (eventType !== "cards.selected" && eventType !== "cards.failed")
    return undefined;
  const report =
    typeof data === "object" && data !== null
      ? (data as Record<string, unknown>)
      : {};
  const identities = Array.isArray(report.identities) ? report.identities : [];
  const colors = Array.isArray(report.colors) ? report.colors : [];
  const choices = Array.isArray(report.choices) ? report.choices : [];
  const hand = identities.map((identity, index) => {
    const card = identity as Record<string, unknown>;
    const color = colors[index] as Record<string, unknown> | undefined;
    return `${index + 1}:${String(color?.color ?? "?")} ${String(card.characterName ?? card.reason ?? "不明")}`;
  });
  const prefix = hand.length ? `5枚の判定 ${hand.join(" / ")}。` : "";
  if (eventType === "cards.failed")
    return `カード認識・選択に失敗しました。${prefix}理由: ${String(report.reason ?? "不明")}`;
  const selected = choices.map((choice) => {
    const item = choice as Record<string, unknown>;
    return `${String(item.slot)}枠=${String(item.kind) === "np" ? "宝具" : "カード"}${Number(item.position) + 1}${typeof item.matchedPreference === "string" ? `(${item.matchedPreference})` : ""}`;
  });
  return `${prefix}選択 ${selected.join(" / ")}。`;
}

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
    severity:
      event.event === "command.failed" || event.event === "cards.failed"
        ? "error"
        : "info",
    eventType: event.event,
    message:
      cardMessage(event.event, envelope?.data) ??
      messages[event.event] ??
      "バックエンドから通知を受信しました。",
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
