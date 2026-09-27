import { describe, expect, it, vi } from "vitest";
import type { SseEvent } from "../events/sseClient";
import type { ValidatedScenario } from "../scenarios/scenario";
import {
  ScenarioEngine,
  type ScenarioEngineOptions,
  type ScenarioProgress,
} from "./scenarioEngine";

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
  it("passes current front members to card selection after a swap", async () => {
    const submit = vi.fn<ScenarioEngineOptions["submit"]>(
      async () => undefined,
    );
    const engine = new ScenarioEngine({
      submit,
      complete: async () => undefined,
      stop: async () => undefined,
      onProgress: () => undefined,
    });
    engine.start({
      schemaVersion: 1,
      members: ["A", "B", "C", "D"],
      commandSources: [["swap(0,3)", "attack_cards('B0')"]],
      commands: [
        [
          { type: "swap", frontIndex: 0, backIndex: 3 },
          {
            type: "attack_cards",
            cardSlots: ["B0", "", ""],
          },
        ],
      ],
    });
    await vi.waitFor(() => expect(submit).toHaveBeenCalledTimes(1));
    const firstId = submit.mock.calls[0][0];
    engine.handleEvent({
      event: "command.completed",
      data: { commandId: firstId },
    } as SseEvent);
    await vi.waitFor(() => expect(submit).toHaveBeenCalledTimes(2));
    expect(submit.mock.calls[1][1]).toMatchObject({
      frontMembers: ["D", "B", "C"],
    });
    engine.cancel();
  });
  it("sends one command at a time and completes after the last SSE event", async () => {
    const submit = vi.fn(async () => undefined);
    const complete = vi.fn(async () => undefined);
    const progress: ScenarioProgress[] = [];
    let id = 0;
    const engine = new ScenarioEngine({
      submit,
      complete,
      stop: async () => undefined,
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

  it("sends only the selected wave and counts progress within it", async () => {
    const submit = vi.fn(async () => undefined);
    const complete = vi.fn(async () => undefined);
    const progress: ScenarioProgress[] = [];
    const engine = new ScenarioEngine({
      submit,
      complete,
      stop: async () => undefined,
      onProgress: (value) => progress.push(value),
      createCommandId: () => "wave-id",
    });
    const multipleWaves: ValidatedScenario = {
      ...scenario,
      commands: [
        scenario.commands[0],
        [{ type: "attack", noblePhantasmIndexes: [] }],
      ],
      commandSources: [scenario.commandSources[0], ["attack()"]],
    };

    engine.start(multipleWaves, 1);
    expect(submit).toHaveBeenCalledOnce();
    expect(submit).toHaveBeenCalledWith(
      "wave-id",
      multipleWaves.commands[1][0],
    );
    expect(progress.at(-1)).toMatchObject({
      groupIndex: 1,
      totalCount: 1,
      completedCount: 0,
    });
    engine.handleEvent(terminalEvent("command.completed", "wave-id"));
    await vi.waitFor(() => expect(complete).toHaveBeenCalledOnce());
    expect(progress.at(-1)).toMatchObject({
      groupIndex: 1,
      totalCount: 1,
      completedCount: 1,
    });
  });

  it("ignores duplicate and unrelated terminal events", async () => {
    const submit = vi.fn(async () => undefined);
    const engine = new ScenarioEngine({
      submit,
      complete: async () => undefined,
      stop: async () => undefined,
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
    const stop = vi.fn(async () => undefined);
    const engine = new ScenarioEngine({
      submit: async () => undefined,
      complete: async () => undefined,
      stop,
      onProgress: (value) => progress.push(value),
      commandTimeoutMs: 100,
      createCommandId: () => "id",
    });
    engine.start(scenario);
    vi.advanceTimersByTime(50);
    engine.setPaused(true);
    vi.advanceTimersByTime(1_000);
    expect(progress.at(-1)?.error).toBeUndefined();
    expect(stop).not.toHaveBeenCalled();
    engine.setPaused(false);
    vi.advanceTimersByTime(51);
    expect(progress.at(-1)?.error).toContain("タイムアウト");
    expect(stop).toHaveBeenCalledOnce();
    vi.useRealTimers();
  });

  it("allows the backend's 50-second battle wait before the default timeout", () => {
    vi.useFakeTimers();
    const progress: ScenarioProgress[] = [];
    const engine = new ScenarioEngine({
      submit: async () => undefined,
      complete: async () => undefined,
      stop: async () => undefined,
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

  it("reports a failed timeout stop request and never sends the next command", async () => {
    vi.useFakeTimers();
    const stop = vi.fn(async () => {
      throw new Error("停止APIに接続できません");
    });
    const submit = vi.fn(async () => undefined);
    const progress: ScenarioProgress[] = [];
    const engine = new ScenarioEngine({
      submit,
      complete: async () => undefined,
      stop,
      onProgress: (value) => progress.push(value),
      commandTimeoutMs: 100,
      createCommandId: () => "id",
    });
    try {
      engine.start(scenario);
      vi.advanceTimersByTime(101);
      await Promise.resolve();
      expect(stop).toHaveBeenCalledOnce();
      expect(progress.at(-1)?.error).toContain("停止要求に失敗");
      engine.handleEvent(terminalEvent("command.completed", "id"));
      expect(submit).toHaveBeenCalledOnce();
    } finally {
      vi.useRealTimers();
    }
  });

  it("stops immediately when a command fails", () => {
    const progress: ScenarioProgress[] = [];
    const engine = new ScenarioEngine({
      submit: async () => undefined,
      complete: async () => undefined,
      stop: async () => undefined,
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
      stop: async () => undefined,
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

  it("requests stop when submission was accepted but its HTTP response was lost", async () => {
    let accepted = false;
    const submit = vi.fn(async () => {
      accepted = true;
      throw new Error("HTTP応答が失われました");
    });
    const stop = vi.fn(async () => {
      expect(accepted).toBe(true);
    });
    const progress: ScenarioProgress[] = [];
    const engine = new ScenarioEngine({
      submit,
      complete: async () => undefined,
      stop,
      onProgress: (value) => progress.push(value),
      createCommandId: () => "id",
    });

    engine.start(scenario);

    await vi.waitFor(() => expect(stop).toHaveBeenCalledOnce());
    expect(progress.at(-1)).toMatchObject({
      completedCount: 0,
      waiting: false,
      error: expect.stringContaining("停止を要求しました"),
    });
    expect(submit).toHaveBeenCalledOnce();
    engine.handleEvent(terminalEvent("command.completed", "id"));
    expect(submit).toHaveBeenCalledOnce();
  });

  it("shows an unresolved stop state when submission and stop requests fail", async () => {
    const progress: ScenarioProgress[] = [];
    const stop = vi.fn(async () => {
      throw new Error("停止APIに接続できません");
    });
    const engine = new ScenarioEngine({
      submit: async () => {
        throw new Error("HTTP応答が失われました");
      },
      complete: async () => undefined,
      stop,
      onProgress: (value) => progress.push(value),
    });

    engine.start(scenario);

    await vi.waitFor(() => expect(stop).toHaveBeenCalledOnce());
    expect(progress.at(-1)?.error).toContain("停止状態を確認できませんでした");
  });

  it("completes an empty scenario without submitting a command", async () => {
    const submit = vi.fn(async () => undefined);
    const complete = vi.fn(async () => undefined);
    const engine = new ScenarioEngine({
      submit,
      complete,
      stop: async () => undefined,
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
