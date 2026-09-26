import type { ScenarioCommand } from "../commands/types";
import type { SseEvent } from "../events/sseClient";
import type { ValidatedScenario } from "../scenarios/scenario";

export type ScenarioProgress = {
  groupIndex: number;
  commandIndex: number;
  completedCount: number;
  totalCount: number;
  waiting: boolean;
  error?: string;
};

export type ScenarioEngineOptions = {
  submit: (commandId: string, command: ScenarioCommand) => Promise<void>;
  complete: () => Promise<void>;
  onProgress: (progress: ScenarioProgress) => void;
  commandTimeoutMs?: number;
  createCommandId?: () => string;
};

type Entry = {
  command: ScenarioCommand;
  groupIndex: number;
  commandIndex: number;
};

export class ScenarioEngine {
  private entries: Entry[] = [];
  private index = 0;
  private currentId?: string;
  private timer?: ReturnType<typeof setTimeout>;
  private remainingMs: number;
  private timerStartedAt = 0;
  private active = false;
  private paused = false;
  private readonly terminalIds = new Set<string>();
  private readonly timeoutMs: number;

  constructor(private readonly options: ScenarioEngineOptions) {
    this.timeoutMs = options.commandTimeoutMs ?? 90_000;
    this.remainingMs = this.timeoutMs;
  }

  start(scenario: ValidatedScenario): void {
    this.cancel();
    this.entries = scenario.commands.flatMap((group, groupIndex) =>
      group.map((command, commandIndex) => ({
        command,
        groupIndex,
        commandIndex,
      })),
    );
    this.index = 0;
    this.active = true;
    this.terminalIds.clear();
    void this.dispatch();
  }

  handleEvent(event: SseEvent): void {
    if (
      !this.active ||
      !event.event ||
      typeof event.data !== "object" ||
      event.data === null
    )
      return;
    const commandId = (event.data as { commandId?: unknown }).commandId;
    if (typeof commandId !== "string" || commandId !== this.currentId) return;
    if (
      !["command.completed", "command.failed", "command.cancelled"].includes(
        event.event,
      )
    )
      return;
    if (this.terminalIds.has(commandId)) return;
    this.terminalIds.add(commandId);
    this.clearTimer();
    if (event.event === "command.completed") {
      this.index += 1;
      this.currentId = undefined;
      void this.dispatch();
    } else {
      this.fail(
        event.event === "command.failed"
          ? "指令の実行に失敗しました"
          : "指令はキャンセルされました",
      );
    }
  }

  setPaused(paused: boolean): void {
    if (!this.active || this.paused === paused) return;
    this.paused = paused;
    if (paused) {
      if (this.timer !== undefined)
        this.remainingMs -= Date.now() - this.timerStartedAt;
      this.clearTimer();
    } else if (this.currentId) this.armTimer();
  }

  cancel(): void {
    this.active = false;
    this.currentId = undefined;
    this.clearTimer();
  }

  private async dispatch(): Promise<void> {
    if (!this.active) return;
    if (this.index >= this.entries.length) {
      try {
        await this.options.complete();
        if (this.active) {
          this.active = false;
          this.emit(false);
        }
      } catch (error) {
        this.fail(
          error instanceof Error ? error.message : "完了処理に失敗しました",
        );
      }
      return;
    }
    const entry = this.entries[this.index];
    const commandId = (this.options.createCommandId ?? createUuidV7)();
    this.currentId = commandId;
    this.remainingMs = this.timeoutMs;
    this.emit(true);
    if (!this.paused) this.armTimer();
    try {
      await this.options.submit(commandId, entry.command);
    } catch (error) {
      if (this.active && this.currentId === commandId)
        this.fail(
          error instanceof Error ? error.message : "指令を送信できませんでした",
        );
    }
  }

  private armTimer(): void {
    this.clearTimer();
    this.timerStartedAt = Date.now();
    this.timer = setTimeout(
      () => this.fail("指令がタイムアウトしました"),
      Math.max(0, this.remainingMs),
    );
  }

  private clearTimer(): void {
    if (this.timer !== undefined) clearTimeout(this.timer);
    this.timer = undefined;
  }

  private fail(message: string): void {
    if (!this.active) return;
    this.active = false;
    this.clearTimer();
    this.emit(false, message);
  }

  private emit(waiting: boolean, error?: string): void {
    const entry =
      this.entries[Math.min(this.index, Math.max(0, this.entries.length - 1))];
    this.options.onProgress({
      groupIndex: entry?.groupIndex ?? 0,
      commandIndex: entry?.commandIndex ?? 0,
      completedCount: this.index,
      totalCount: this.entries.length,
      waiting,
      error,
    });
  }
}

export function createUuidV7(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  let timestamp = Date.now();
  for (let index = 5; index >= 0; index -= 1) {
    bytes[index] = timestamp & 0xff;
    timestamp = Math.floor(timestamp / 256);
  }
  bytes[6] = 0x70 | (bytes[6] & 0x0f);
  bytes[8] = 0x80 | (bytes[8] & 0x3f);
  const hex = [...bytes].map((value) => value.toString(16).padStart(2, "0"));
  return `${hex.slice(0, 4).join("")}-${hex.slice(4, 6).join("")}-${hex.slice(6, 8).join("")}-${hex.slice(8, 10).join("")}-${hex.slice(10).join("")}`;
}
