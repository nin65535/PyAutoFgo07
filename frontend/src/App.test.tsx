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
    expect(
      await screen.findByRole("img", { name: "バックエンド：接続済み" }),
    ).toHaveAttribute("title", "バックエンド：接続済み");
    expect(
      screen.getByRole("img", { name: "実行状態：待機中" }),
    ).toHaveAttribute("title", "実行状態：待機中");
    expect(screen.getByRole("button", { name: "緊急停止" })).toBeEnabled();
    expect(
      screen.queryByRole("heading", { name: "Control" }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Stages" })).toBeInTheDocument();
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
    expect(
      await screen.findByRole("img", { name: "バックエンド：切断" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("操作できません");
    expect(screen.getByRole("button", { name: "緊急停止" })).toBeDisabled();
  });

  it("shows selected Stage members on separate lines and a compact validation state", async () => {
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
    expect(screen.getByText("A")).toBeInTheDocument();
    expect(screen.getByText("B")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Alpha/ }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("命令グループ")).not.toBeInTheDocument();
    expect(screen.queryByText(/wave 1 \/ グループ/)).not.toBeInTheDocument();
    expect(screen.queryByText(/2026\/09\/22/)).not.toBeInTheDocument();
    const showAll = screen.getByRole("button", { name: "Allの命令を見る" });
    fireEvent.click(showAll);
    expect(showAll).toHaveAttribute("aria-expanded", "true");
    expect(
      screen.getByRole("region", { name: "Allの命令詳細" }),
    ).toHaveTextContent("skill(0)");
    expect(
      screen.getByRole("region", { name: "Allの命令詳細" }),
    ).toHaveTextContent("attack()");
    fireEvent.click(showAll);
    expect(
      screen.queryByRole("region", { name: "Allの命令詳細" }),
    ).not.toBeInTheDocument();
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
    expect(
      screen.getByText("検証に失敗したため実行できません。"),
    ).toBeInTheDocument();
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
    const start = await screen.findByRole("button", { name: "All(0/1)" });
    expect(
      screen.getByRole("heading", { name: "Control" }),
    ).toBeInTheDocument();
    expect(start).toBeEnabled();
    fireEvent.click(start);
    await waitFor(() => expect(act).toHaveBeenCalledWith("start"));
    expect(
      screen.queryByRole("button", { name: /Alpha/ }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "一時停止" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "All(0/1)" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "All(0/1)" })).toHaveClass(
      "wave-action__active",
    );
    expect(
      screen.getByRole("button", { name: "Controlを閉じる" }),
    ).toBeDisabled();
  });

  it("closes Control and clears the selected Stage while idle", async () => {
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
    render(
      <App
        createSseClient={clientFactory("active")}
        scenarioApi={scenarioApi}
        executionApi={idleExecutionApi}
      />,
    );
    const stage = await screen.findByRole("button", { name: /Alpha/ });
    fireEvent.click(stage);
    expect(
      await screen.findByRole("heading", { name: "Control" }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Controlを閉じる" }));
    expect(
      screen.queryByRole("heading", { name: "Control" }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Alpha/ })).toBeInTheDocument();
  });

  it("starts only the selected wave and locks start buttons during execution", async () => {
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
    const submit = vi.fn<ExecutionApi["submit"]>(async () => undefined);
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
    expect(
      await screen.findByRole("button", { name: "Wave2(0/1)" }),
    ).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "Controlを閉じる" }));
    fireEvent.click(screen.getByRole("button", { name: /Beta/ }));
    fireEvent.click(
      await screen.findByRole("button", { name: "Wave2の命令を見る" }),
    );
    const detail = screen.getByRole("region", { name: "Wave2の命令詳細" });
    const command = detail.querySelector("li");
    expect(command).not.toBeNull();
    vi.spyOn(detail, "getBoundingClientRect").mockReturnValue({
      top: 100,
      bottom: 200,
    } as DOMRect);
    vi.spyOn(command!, "getBoundingClientRect").mockReturnValue({
      top: 230,
      bottom: 250,
    } as DOMRect);
    fireEvent.click(await screen.findByRole("button", { name: "Wave2(0/1)" }));
    await waitFor(() =>
      expect(submit).toHaveBeenCalledWith(expect.any(String), {
        type: "attack",
        noblePhantasmIndexes: [],
      }),
    );
    expect(screen.getByRole("button", { name: "Wave2(0/1)" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Wave2(0/1)" })).toHaveClass(
      "wave-action__active",
    );
    expect(screen.getByRole("button", { name: "All(0/2)" })).not.toHaveClass(
      "wave-action__active",
    );
    expect(
      screen.queryByRole("button", { name: /Alpha/ }),
    ).not.toBeInTheDocument();
    expect(screen.getByText(/wave 2: 0\/1件完了/)).toBeInTheDocument();
    expect(
      screen
        .getByRole("region", { name: "Wave2の命令詳細" })
        .querySelector("[aria-current='step']"),
    ).toHaveTextContent("attack()");
    expect(detail.scrollTop).toBe(54);
  });

  it("updates All and Wave completed counts from command completion events", async () => {
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
          members: ["A"],
          commands: [["skill(0)"], ["attack()"]],
        },
      }),
    };
    const submit = vi.fn<ExecutionApi["submit"]>(async () => undefined);
    let onEvent: SseClientOptions["onEvent"] = () => undefined;
    render(
      <App
        createSseClient={(options) => {
          onEvent = options.onEvent;
          return {
            connect: async () => options.onStateChange("active"),
            close: () => undefined,
          };
        }}
        scenarioApi={scenarioApi}
        executionApi={{ ...idleExecutionApi, submit }}
      />,
    );
    fireEvent.click(await screen.findByRole("button", { name: /Alpha/ }));
    fireEvent.click(await screen.findByRole("button", { name: "All(0/2)" }));
    await waitFor(() => expect(submit).toHaveBeenCalledTimes(1));
    const firstId = submit.mock.calls[0][0];
    onEvent({ event: "command.completed", data: { commandId: firstId } });
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "All(1/2)" }),
      ).toBeInTheDocument(),
    );
    expect(
      screen.getByRole("button", { name: "Wave1(1/1)" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Wave2(0/1)" }),
    ).toBeInTheDocument();
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
