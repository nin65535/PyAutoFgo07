import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { App, type AppProps } from "./App";
import type { SseClientOptions } from "./events/sseClient";

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
    render(<App createSseClient={clientFactory("active")} />);
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
    render(<App createSseClient={clientFactory("inactive")} />);
    expect(await screen.findByText("切断")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("操作できません");
    expect(screen.getByRole("button", { name: "緊急停止" })).toBeDisabled();
  });
});
