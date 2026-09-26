import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { App, type AppProps } from "./App";
import type { SseClientOptions } from "./events/sseClient";
import type { ScenarioApi } from "./scenarios/api";
import type { ExecutionApi, ExecutionState } from "./execution/api";

const emptyScenarioApi: ScenarioApi = {
  list: async () => [],
  get: async () => {
    throw new Error("not found");
  },
};

const snapshot = (state: ExecutionState) => ({
  state,
  currentCommandId: null,
  queuedCount: 0,
  acceptingCommands: state !== "emergency_stopping",
});
const idleExecutionApi: ExecutionApi = {
  status: async () => snapshot("idle"),
  act: async (action) => snapshot(action === "start" ? "running" : "idle"),
  submit: async () => undefined,
  complete: async () => snapshot("completed"),
};

const executionApiWith = (act: ExecutionApi["act"]): ExecutionApi => ({
  status: async () => snapshot("idle"),
  act,
  submit: async () => undefined,
  complete: async () => snapshot("completed"),
});

function clientFactory(
  state: "active" | "inactive",
): NonNullable<AppProps["createSseClient"]> {
  return (options: SseClientOptions) => ({
    connect: async () => options.onStateChange(state),
    close: () => undefined,
  });
}

describe("App", () => {
  it("renders the narrow SPA's persistent status and main sections", async () => {
    render(
      <App
        createSseClient={clientFactory("active")}
        scenarioApi={emptyScenarioApi}
        executionApi={idleExecutionApi}
      />,
    );
    expect(
      screen.getByRole("heading", { name: "autoFgo" }),
    ).toBeInTheDocument();
    expect(await screen.findByText("接続済み")).toBeInTheDocument();
    expect(screen.getAllByText("待機中")).toHaveLength(2);
    expect(screen.getByRole("button", { name: "緊急停止" })).toBeEnabled();
    expect(
      screen.getByRole("heading", { name: "実行コントロール" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "操作手順" }),
    ).toBeInTheDocument();
    expect(screen.getByText("ログと詳細")).toBeInTheDocument();
  });

  it("makes backend-dependent actions inactive after disconnection", async () => {
    render(
      <App
        createSseClient={clientFactory("inactive")}
        scenarioApi={emptyScenarioApi}
        executionApi={idleExecutionApi}
      />,
    );
    expect(await screen.findByText("切断")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("操作できません");
    expect(screen.getByRole("button", { name: "緊急停止" })).toBeDisabled();
  });

  it("shows a selected valid scenario's members, groups, and executable state", async () => {
    const scenarioApi: ScenarioApi = {
      list: async () => [
        {
          id: "alpha",
          displayName: "Alpha",
          modifiedAt: "2026-09-22T00:00:00.000Z",
        },
      ],
      get: async () => ({
        id: "alpha",
        displayName: "Alpha",
        modifiedAt: "2026-09-22T00:00:00.000Z",
        content: {
          schemaVersion: 1,
          members: ["A", "B"],
          commands: [["skill(0)", "attack()"]],
        },
      }),
    };
    render(
      <App
        createSseClient={clientFactory("active")}
        scenarioApi={scenarioApi}
        executionApi={idleExecutionApi}
      />,
    );
    fireEvent.click(await screen.findByRole("button", { name: /Alpha/ }));
    expect(await screen.findByText("実行可能")).toBeInTheDocument();
    expect(screen.getByText("A / B")).toBeInTheDocument();
    expect(
      screen.getByText("wave 1 / グループ 1（2命令）"),
    ).toBeInTheDocument();
    expect(screen.getByText(/検証に成功しました/)).toBeInTheDocument();
  });

  it("shows a command location and reason when validation fails", async () => {
    const scenarioApi: ScenarioApi = {
      list: async () => [
        {
          id: "bad",
          displayName: "Bad file",
          modifiedAt: "2026-09-22T00:00:00.000Z",
        },
      ],
      get: async () => ({
        id: "bad",
        displayName: "Bad file",
        modifiedAt: "2026-09-22T00:00:00.000Z",
        content: { schemaVersion: 1, members: ["A"], commands: [["danger()"]] },
      }),
    };
    render(
      <App
        createSseClient={clientFactory("active")}
        scenarioApi={scenarioApi}
        executionApi={idleExecutionApi}
      />,
    );
    fireEvent.click(await screen.findByRole("button", { name: /Bad file/ }));
    expect(await screen.findByText(/グループ1・命令1/)).toHaveTextContent(
      "未対応の命令",
    );
    expect(screen.getByText("要確認")).toBeInTheDocument();
  });

  it("enables mouse controls only for transitions allowed by the current state", async () => {
    const scenarioApi: ScenarioApi = {
      list: async () => [
        {
          id: "alpha",
          displayName: "Alpha",
          modifiedAt: "2026-09-22T00:00:00.000Z",
        },
      ],
      get: async () => ({
        id: "alpha",
        displayName: "Alpha",
        modifiedAt: "2026-09-22T00:00:00.000Z",
        content: { schemaVersion: 1, members: ["A"], commands: [["attack()"]] },
      }),
    };
    const act = vi.fn(
      async (
        action: "start" | "pause" | "resume" | "stop" | "emergency-stop",
      ) =>
        snapshot(
          action === "start"
            ? "running"
            : action === "pause"
              ? "paused"
              : "stopped",
        ),
    );
    render(
      <App
        createSseClient={clientFactory("active")}
        scenarioApi={scenarioApi}
        executionApi={executionApiWith(act)}
      />,
    );

    fireEvent.click(await screen.findByRole("button", { name: /Alpha/ }));
    const start = await screen.findByRole("button", { name: "開始" });
    expect(start).toBeDisabled();
    fireEvent.click(screen.getByRole("radio", { name: "全wave（1命令）" }));
    await waitFor(() => expect(start).toBeEnabled());
    fireEvent.click(start);
    await waitFor(() => expect(act).toHaveBeenCalledWith("start"));
    expect(screen.getByRole("button", { name: /Alpha/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: "一時停止" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "開始" })).toBeDisabled();
  });

  it("requires a fresh wave choice after changing scenarios and locks it during execution", async () => {
    const scenarioApi: ScenarioApi = {
      list: async () =>
        ["Alpha", "Beta"].map((name) => ({
          id: name,
          displayName: name,
          modifiedAt: "2026-09-22T00:00:00.000Z",
        })),
      get: async (id) => ({
        id,
        displayName: id,
        modifiedAt: "2026-09-22T00:00:00.000Z",
        content: {
          schemaVersion: 1,
          members: ["A"],
          commands: [["skill(0)"], ["attack()"]],
        },
      }),
    };
    const submit = vi.fn(async () => undefined);
    const executionApi: ExecutionApi = {
      ...idleExecutionApi,
      submit,
    };
    render(
      <App
        createSseClient={clientFactory("active")}
        scenarioApi={scenarioApi}
        executionApi={executionApi}
      />,
    );

    fireEvent.click(await screen.findByRole("button", { name: /Alpha/ }));
    fireEvent.click(
      await screen.findByRole("radio", { name: "wave 2（グループ 2・1命令）" }),
    );
    expect(screen.getByText("開始対象: wave 2")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Beta/ }));
    expect(screen.getByRole("button", { name: "開始" })).toBeDisabled();
    expect(await screen.findByText("開始対象: 未確認")).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("radio", { name: "wave 2（グループ 2・1命令）" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "開始" }));
    await waitFor(() =>
      expect(submit).toHaveBeenCalledWith(expect.any(String), {
        type: "attack",
        noblePhantasmIndexes: [],
      }),
    );
    expect(
      screen.getByRole("radio", { name: "wave 2（グループ 2・1命令）" }),
    ).toBeDisabled();
    expect(screen.getByRole("button", { name: /Alpha/ })).toBeDisabled();
    expect(screen.getByText(/wave 2: 0\/1件完了/)).toBeInTheDocument();
  });

  it("sends emergency stop from the persistent control", async () => {
    const act = vi.fn(async () => snapshot("emergency_stopping"));
    render(
      <App
        createSseClient={clientFactory("active")}
        scenarioApi={emptyScenarioApi}
        executionApi={executionApiWith(act)}
      />,
    );
    fireEvent.click(await screen.findByRole("button", { name: "緊急停止" }));
    await waitFor(() => expect(act).toHaveBeenCalledWith("emergency-stop"));
  });

  it("shows user-facing event text separately from developer details", async () => {
    render(
      <App
        createSseClient={(options) => ({
          connect: async () => {
            options.onStateChange("active");
            options.onEvent({
              event: "command.failed",
              id: "9",
              data: {
                eventId: 9,
                occurredAt: "2026-09-25T00:00:00Z",
                commandId: "cmd-9",
                data: { code: "COMMAND_EXECUTION_FAILED" },
              },
            });
          },
          close: () => undefined,
        })}
        scenarioApi={emptyScenarioApi}
        executionApi={idleExecutionApi}
      />,
    );
    fireEvent.click(await screen.findByText("ログと詳細"));
    expect(screen.getByText("指令の実行に失敗しました。")).toBeInTheDocument();
    expect(screen.getByText("command.failed / cmd-9")).toBeInTheDocument();
    expect(screen.getByText("開発者向け詳細")).toBeInTheDocument();
  });
});
