import { describe, expect, it } from "vitest";
import { connectionEntry, entryFromSse } from "./logEntries";

describe("log entries", () => {
  it("separates a user message from SSE developer details", () => {
    const entry = entryFromSse({
      event: "command.failed",
      id: "3",
      data: {
        eventId: 3,
        occurredAt: "2026-09-25T00:00:00Z",
        commandId: "cmd-1",
        data: { code: "COMMAND_EXECUTION_FAILED" },
      },
    });
    expect(entry).toMatchObject({
      severity: "error",
      message: "指令の実行に失敗しました。",
      commandId: "cmd-1",
      detail: { code: "COMMAND_EXECUTION_FAILED" },
    });
  });

  it("marks disconnection as an error", () => {
    expect(connectionEntry("inactive").severity).toBe("error");
  });
});
