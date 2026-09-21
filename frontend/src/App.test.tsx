import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { App, type AppProps } from "./App";
import type { SseClientOptions } from "./events/sseClient";
import type { ScenarioApi } from "./scenarios/api";

const emptyScenarioApi: ScenarioApi = {
  list: async () => [],
  get: async () => {
    throw new Error("not found");
  },
};

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
      />,
    );
    expect(
      screen.getByRole("heading", { name: "autoFgo" }),
    ).toBeInTheDocument();
    expect(await screen.findByText("接続済み")).toBeInTheDocument();
    expect(screen.getByText("待機中")).toBeInTheDocument();
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
      />,
    );
    fireEvent.click(await screen.findByRole("button", { name: /Alpha/ }));
    expect(await screen.findByText("実行可能")).toBeInTheDocument();
    expect(screen.getByText("A / B")).toBeInTheDocument();
    expect(screen.getByText("グループ 1（2命令）")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("検証に成功");
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
      />,
    );
    fireEvent.click(await screen.findByRole("button", { name: /Bad file/ }));
    expect(await screen.findByText(/グループ1・命令1/)).toHaveTextContent(
      "未対応の命令",
    );
    expect(screen.getByText("要確認")).toBeInTheDocument();
  });
});
