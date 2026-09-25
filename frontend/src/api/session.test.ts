import { beforeEach, describe, expect, it, vi } from "vitest";

describe("session credentials", () => {
  beforeEach(() => {
    vi.resetModules();
    history.replaceState(
      null,
      "",
      "/#autofgoSession=session-1&autofgoToken=secret-token",
    );
  });

  it("reads credentials once, removes the fragment, and adds authentication headers", async () => {
    const { authenticatedHeaders, getSessionCredentials } =
      await import("./session");

    expect(getSessionCredentials()).toEqual({
      sessionId: "session-1",
      token: "secret-token",
    });
    expect(location.hash).toBe("");
    const headers = authenticatedHeaders({ Accept: "application/json" });
    expect(headers.get("X-AutoFgo-Session-Id")).toBe("session-1");
    expect(headers.get("Authorization")).toBe("Bearer secret-token");
  });
});
