import { useEffect, useState } from "react";
import {
  SseClient,
  type ConnectionState,
  type SseClientOptions,
  type SseEvent,
} from "./events/sseClient";
import { createScenarioApi, type ScenarioApi } from "./scenarios/api";
import {
  validateScenario,
  type ScenarioSummary,
  type ScenarioValidation,
} from "./scenarios/scenario";

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
  scenarioApi?: ScenarioApi;
};

const defaultCreateSseClient = (options: SseClientOptions): SseConnection =>
  new SseClient(options);
const defaultScenarioApi = createScenarioApi();

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

export function App({
  createSseClient = defaultCreateSseClient,
  scenarioApi = defaultScenarioApi,
}: AppProps) {
  const [connection, setConnection] = useState<ConnectionState>("connecting");
  const [execution, setExecution] = useState<ExecutionState>("idle");
  const [currentCommand, setCurrentCommand] = useState<string>();
  const [scenarios, setScenarios] = useState<ScenarioSummary[]>([]);
  const [selected, setSelected] = useState<ScenarioSummary>();
  const [validation, setValidation] = useState<ScenarioValidation>();
  const [scenarioStatus, setScenarioStatus] = useState<
    "loading" | "ready" | "empty" | "error"
  >("loading");
  const [scenarioError, setScenarioError] = useState<string>();

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

  useEffect(() => {
    let active = true;
    scenarioApi
      .list()
      .then((items) => {
        if (!active) return;
        setScenarios(items);
        setScenarioStatus(items.length > 0 ? "ready" : "empty");
      })
      .catch((error: unknown) => {
        if (!active) return;
        setScenarioError(
          error instanceof Error ? error.message : "一覧を読み込めませんでした",
        );
        setScenarioStatus("error");
      });
    return () => {
      active = false;
    };
  }, [scenarioApi]);

  const selectScenario = async (summary: ScenarioSummary) => {
    setSelected(summary);
    setValidation(undefined);
    setScenarioError(undefined);
    try {
      const detail = await scenarioApi.get(summary.id);
      setValidation(validateScenario(detail.content));
    } catch (error) {
      setScenarioError(
        error instanceof Error
          ? error.message
          : "操作手順を読み込めませんでした",
      );
    }
  };

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
          <span className="coming-soon">
            {validation?.valid ? "実行可能" : selected ? "要確認" : "未選択"}
          </span>
        </div>
        {scenarioStatus === "loading" && (
          <p className="empty-state">一覧を読み込み中です。</p>
        )}
        {scenarioStatus === "empty" && (
          <p className="empty-state">利用できる操作手順はありません。</p>
        )}
        {scenarioStatus === "error" && (
          <p className="scenario-error" role="alert">
            {scenarioError}
          </p>
        )}
        {scenarioStatus === "ready" && (
          <div className="scenario-list" aria-label="操作手順一覧">
            {scenarios.map((scenario) => (
              <button
                className={
                  selected?.id === scenario.id
                    ? "scenario-item scenario-item--selected"
                    : "scenario-item"
                }
                key={scenario.id}
                type="button"
                aria-pressed={selected?.id === scenario.id}
                onClick={() => void selectScenario(scenario)}
              >
                <span>{scenario.displayName}</span>
                <time dateTime={scenario.modifiedAt}>
                  {new Date(scenario.modifiedAt).toLocaleString("ja-JP")}
                </time>
              </button>
            ))}
          </div>
        )}
        {scenarioError && scenarioStatus !== "error" && (
          <p className="scenario-error" role="alert">
            {selected?.displayName}: {scenarioError}
          </p>
        )}
        {selected && validation?.valid && (
          <div className="scenario-detail">
            <h3>{selected.displayName}</h3>
            <dl className="scenario-facts">
              <div>
                <dt>メンバー</dt>
                <dd>{validation.scenario.members.join(" / ")}</dd>
              </div>
              <div>
                <dt>命令グループ</dt>
                <dd>{validation.scenario.commands.length}件</dd>
              </div>
              <div>
                <dt>命令数</dt>
                <dd>{validation.scenario.commands.flat().length}件</dd>
              </div>
            </dl>
            {validation.scenario.commandSources.map((group, index) => (
              <details className="command-group" key={index}>
                <summary>
                  グループ {index + 1}（{group.length}命令）
                </summary>
                <ol>
                  {group.map((command, commandIndex) => (
                    <li key={commandIndex}>{command}</li>
                  ))}
                </ol>
              </details>
            ))}
            <p className="validation-ok" role="status">
              検証に成功しました。この操作手順は実行可能です。
            </p>
          </div>
        )}
        {selected && validation && !validation.valid && (
          <div className="scenario-detail">
            <h3>{selected.displayName}</h3>
            <p className="scenario-error">検証に失敗したため実行できません。</p>
            <ul className="validation-errors">
              {validation.errors.map((error, index) => (
                <li key={index}>
                  {error.location === "scenario"
                    ? "操作手順全体"
                    : `グループ${error.location.groupIndex + 1}・命令${error.location.commandIndex + 1}`}
                  : {error.message}
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>

      <details className="panel details-panel">
        <summary>ログと詳細</summary>
        <p className="empty-state">表示できるログはまだありません。</p>
      </details>
    </main>
  );
}
