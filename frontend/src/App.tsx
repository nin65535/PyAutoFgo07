import { useEffect, useState } from "react";
import {
  SseClient,
  type ConnectionState,
  type SseClientOptions,
  type SseEvent,
} from "./events/sseClient";

type ExecutionState =
  | "idle"
  | "running"
  | "pausing"
  | "paused"
  | "stopping"
  | "stopped"
  | "completed"
  | "error"
  | "emergency_stopping";
type SseConnection = Pick<SseClient, "connect" | "close">;
export type AppProps = {
  createSseClient?: (options: SseClientOptions) => SseConnection;
};

const defaultCreateSseClient = (options: SseClientOptions): SseConnection =>
  new SseClient(options);

const connectionLabels: Record<ConnectionState, string> = {
  connecting: "接続中",
  active: "接続済み",
  inactive: "切断",
};
const executionLabels: Record<ExecutionState, string> = {
  idle: "待機中",
  running: "実行中",
  pausing: "一時停止処理中",
  paused: "一時停止中",
  stopping: "停止処理中",
  stopped: "停止済み",
  completed: "完了",
  error: "エラー",
  emergency_stopping: "緊急停止処理中",
};

function executionStateFrom(event: SseEvent): ExecutionState | undefined {
  if (
    event.event !== "execution.state_changed" ||
    typeof event.data !== "object" ||
    event.data === null
  )
    return undefined;
  const state = (event.data as { data?: { currentState?: unknown } }).data
    ?.currentState;
  return typeof state === "string" && state in executionLabels
    ? (state as ExecutionState)
    : undefined;
}

export function App({ createSseClient = defaultCreateSseClient }: AppProps) {
  const [connection, setConnection] = useState<ConnectionState>("connecting");
  const [execution, setExecution] = useState<ExecutionState>("idle");
  const [currentCommand, setCurrentCommand] = useState<string>();

  useEffect(() => {
    const client = createSseClient({
      url: "/api/events",
      onStateChange: setConnection,
      onEvent: (event) => {
        const nextState = executionStateFrom(event);
        if (nextState) setExecution(nextState);
        if (event.event === "command.started" && event.data) {
          const commandId = (event.data as { commandId?: unknown }).commandId;
          setCurrentCommand(
            typeof commandId === "string" ? commandId : "処理中の指令",
          );
        }
        if (
          ["command.completed", "command.failed", "command.cancelled"].includes(
            event.event ?? "",
          )
        )
          setCurrentCommand(undefined);
      },
    });
    void client.connect();
    return () => client.close();
  }, [createSseClient]);

  const inactive = connection !== "active";
  return (
    <main className="app-shell">
      <header className="app-header">
        <div>
          <p className="eyebrow">AUTO PLAY CONSOLE</p>
          <h1>autoFgo</h1>
        </div>
        <span className={`status-dot status-dot--${connection}`} aria-hidden />
      </header>

      <section className="sticky-status" aria-label="現在の状態">
        <dl className="status-grid">
          <div>
            <dt>バックエンド</dt>
            <dd data-testid="connection-state">
              {connectionLabels[connection]}
            </dd>
          </div>
          <div>
            <dt>実行状態</dt>
            <dd>{executionLabels[execution]}</dd>
          </div>
        </dl>
        <p className="current-command" title={currentCommand}>
          {currentCommand
            ? `指令: ${currentCommand}`
            : "実行中の指令はありません"}
        </p>
        <button className="emergency-button" type="button" disabled={inactive}>
          緊急停止
        </button>
      </section>

      {connection === "inactive" && (
        <p className="connection-alert" role="alert">
          バックエンドとの接続が切れました。この画面からは操作できません。
        </p>
      )}

      <section className="panel" aria-labelledby="controls-title">
        <div className="section-heading">
          <div>
            <p className="section-number">01</p>
            <h2 id="controls-title">実行コントロール</h2>
          </div>
          <span className="coming-soon">準備中</span>
        </div>
        <div className="control-grid">
          <button type="button" disabled>
            開始
          </button>
          <button type="button" disabled>
            一時停止
          </button>
          <button type="button" disabled>
            再開
          </button>
          <button type="button" disabled>
            通常停止
          </button>
        </div>
      </section>

      <section className="panel" aria-labelledby="scenario-title">
        <div className="section-heading">
          <div>
            <p className="section-number">02</p>
            <h2 id="scenario-title">操作手順</h2>
          </div>
          <span className="coming-soon">未選択</span>
        </div>
        <p className="empty-state">
          利用できる操作手順を読み込む準備ができています。
        </p>
      </section>

      <details className="panel details-panel">
        <summary>ログと詳細</summary>
        <p className="empty-state">表示できるログはまだありません。</p>
      </details>
    </main>
  );
}
