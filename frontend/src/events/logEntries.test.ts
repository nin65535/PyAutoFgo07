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

  it("shows card decisions and failure reasons", () => {
    const data = {
      eventId: 4,
      commandId: "cmd-2",
      data: {
        colors: [{ color: "B" }],
        identities: [{ characterName: "A", reason: "matched" }],
        choices: [
          { slot: 1, kind: "card", position: 0, matchedPreference: "B0" },
        ],
      },
    };
    expect(entryFromSse({ event: "cards.selected", data })?.message).toContain(
      "1枠=カード1(B0)",
    );
    expect(
      entryFromSse({
        event: "cards.failed",
        data: { ...data, data: { ...data.data, reason: "low_similarity" } },
      }),
    ).toMatchObject({
      severity: "error",
      commandId: "cmd-2",
    });
    expect(
      entryFromSse({
        event: "cards.failed",
        data: { ...data, data: { reason: "low_similarity" } },
      })?.message,
    ).toContain("low_similarity");
  });
});
