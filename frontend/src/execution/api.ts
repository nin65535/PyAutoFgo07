export type ExecutionState =
  | "idle"
  | "running"
  | "pausing"
  | "paused"
  | "stopping"
  | "stopped"
  | "completed"
  | "error"
  | "emergency_stopping";

export type ExecutionSnapshot = {
  state: ExecutionState;
  currentCommandId: string | null;
  queuedCount: number;
  acceptingCommands: boolean;
};

export type ExecutionAction =
  "start" | "pause" | "resume" | "stop" | "emergency-stop";

export type ExecutionApi = {
  status(): Promise<ExecutionSnapshot>;
  act(action: ExecutionAction): Promise<ExecutionSnapshot>;
};

export function createExecutionApi(
  fetchImpl: typeof fetch = fetch,
): ExecutionApi {
  const request = async (path: string, init?: RequestInit) => {
    const response = await fetchImpl(`/api/commands${path}`, init);
    const body = (await response.json()) as {
      data?: ExecutionSnapshot;
      error?: { message?: string };
    };
    if (!response.ok || !body.data) {
      throw new Error(body.error?.message ?? "実行操作に失敗しました");
    }
    return body.data;
  };
  return {
    status: () => request("/status"),
    act: (action) => request(`/${action}`, { method: "POST" }),
  };
}
