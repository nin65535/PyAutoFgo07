import { describe, expect, it, vi } from "vitest";
import type { SseEvent } from "../events/sseClient";
import type { ValidatedScenario } from "../scenarios/scenario";
import { ScenarioEngine, type ScenarioProgress } from "./scenarioEngine";

const scenario: ValidatedScenario = {
  schemaVersion: 1,
  members: ["A"],
  commandSources: [["skill(0)", "attack()"]],
  commands: [
    [
      { type: "skill", skillIndex: 0 },
      { type: "attack", noblePhantasmIndexes: [] },
    ],
  ],
};

const terminalEvent = (type: string, commandId: string): SseEvent => ({
  event: type,
  data: { commandId },
});

describe("ScenarioEngine", () => {
  it("sends one command at a time and completes after the last SSE event", async () => {
    const submit = vi.fn(async () => undefined);
    const complete = vi.fn(async () => undefined);
    const progress: ScenarioProgress[] = [];
    let id = 0;
    const engine = new ScenarioEngine({
      submit,
      complete,
      onProgress: (value) => progress.push(value),
      createCommandId: () => `id-${++id}`,
    });

    engine.start(scenario);
    expect(submit).toHaveBeenCalledTimes(1);
    engine.handleEvent(terminalEvent("command.completed", "id-1"));
    await vi.waitFor(() => expect(submit).toHaveBeenCalledTimes(2));
    engine.handleEvent(terminalEvent("command.completed", "id-2"));
    await vi.waitFor(() => expect(complete).toHaveBeenCalledOnce());
    expect(progress.at(-1)).toMatchObject({
      completedCount: 2,
      waiting: false,
    });
  });

  it("ignores duplicate and unrelated terminal events", async () => {
    const submit = vi.fn(async () => undefined);
    const engine = new ScenarioEngine({
      submit,
      complete: async () => undefined,
      onProgress: () => undefined,
      createCommandId: () => "stable-id",
    });
    engine.start(scenario);
    engine.handleEvent(terminalEvent("command.completed", "other-id"));
    engine.handleEvent(terminalEvent("command.completed", "stable-id"));
    engine.handleEvent(terminalEvent("command.completed", "stable-id"));
    await vi.waitFor(() => expect(submit).toHaveBeenCalledTimes(2));
  });

  it("reports a timeout but does not count paused time", () => {
    vi.useFakeTimers();
    const progress: ScenarioProgress[] = [];
    const engine = new ScenarioEngine({
      submit: async () => undefined,
      complete: async () => undefined,
      onProgress: (value) => progress.push(value),
      commandTimeoutMs: 100,
      createCommandId: () => "id",
    });
    engine.start(scenario);
    vi.advanceTimersByTime(50);
    engine.setPaused(true);
    vi.advanceTimersByTime(1_000);
    expect(progress.at(-1)?.error).toBeUndefined();
    engine.setPaused(false);
    vi.advanceTimersByTime(51);
    expect(progress.at(-1)?.error).toContain("タイムアウト");
    vi.useRealTimers();
  });

  it("allows the backend's 50-second battle wait before the default timeout", () => {
    vi.useFakeTimers();
    const progress: ScenarioProgress[] = [];
    const engine = new ScenarioEngine({
      submit: async () => undefined,
      complete: async () => undefined,
      onProgress: (value) => progress.push(value),
      createCommandId: () => "id",
    });

    engine.start(scenario);
    vi.advanceTimersByTime(50_000);
    expect(progress.at(-1)?.error).toBeUndefined();
    vi.advanceTimersByTime(40_001);
    expect(progress.at(-1)?.error).toContain("タイムアウト");
    vi.useRealTimers();
  });

  it("stops immediately when a command fails", () => {
    const progress: ScenarioProgress[] = [];
    const engine = new ScenarioEngine({
      submit: async () => undefined,
      complete: async () => undefined,
      onProgress: (value) => progress.push(value),
      createCommandId: () => "id",
    });
    engine.start(scenario);
    engine.handleEvent(terminalEvent("command.failed", "id"));
    expect(progress.at(-1)?.error).toContain("失敗");
  });

  it("stops immediately when a command is cancelled", () => {
    const progress: ScenarioProgress[] = [];
    const engine = new ScenarioEngine({
      submit: async () => undefined,
      complete: async () => undefined,
      onProgress: (value) => progress.push(value),
      createCommandId: () => "id",
    });
    engine.start(scenario);

    engine.handleEvent(terminalEvent("command.cancelled", "id"));

    expect(progress.at(-1)).toMatchObject({
      completedCount: 0,
      waiting: false,
      error: "指令はキャンセルされました",
    });
  });

  it("reports submission failures without dispatching the next command", async () => {
    const submit = vi.fn(async () => {
      throw new Error("送信エラー");
    });
    const progress: ScenarioProgress[] = [];
    const engine = new ScenarioEngine({
      submit,
      complete: async () => undefined,
      onProgress: (value) => progress.push(value),
      createCommandId: () => "id",
    });

    engine.start(scenario);

    await vi.waitFor(() =>
      expect(progress.at(-1)).toMatchObject({
        completedCount: 0,
        waiting: false,
        error: "送信エラー",
      }),
    );
    expect(submit).toHaveBeenCalledOnce();
  });

  it("completes an empty scenario without submitting a command", async () => {
    const submit = vi.fn(async () => undefined);
    const complete = vi.fn(async () => undefined);
    const engine = new ScenarioEngine({
      submit,
      complete,
      onProgress: () => undefined,
    });
    const emptyScenario: ValidatedScenario = {
      schemaVersion: 1,
      members: [],
      commandSources: [],
      commands: [],
    };

    engine.start(emptyScenario);

    await vi.waitFor(() => expect(complete).toHaveBeenCalledOnce());
    expect(submit).not.toHaveBeenCalled();
  });
});
