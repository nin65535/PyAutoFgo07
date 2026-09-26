import { useCallback, useEffect, useRef, useState } from "react";
import {
  SseClient,
  type ConnectionState,
  type SseClientOptions,
  type SseEvent,
} from "./events/sseClient";
import {
  connectionEntry,
  entryFromSse,
  localEntry,
  type LogEntry,
} from "./events/logEntries";
import { createScenarioApi, type ScenarioApi } from "./scenarios/api";
import {
  createExecutionApi,
  type ExecutionAction,
  type ExecutionApi,
  type ExecutionState,
} from "./execution/api";
import {
  ScenarioEngine,
  type ScenarioProgress,
} from "./execution/scenarioEngine";
import {
  validateScenario,
  type ScenarioSummary,
  type ScenarioValidation,
} from "./scenarios/scenario";

type SseConnection = Pick<SseClient, "connect" | "close">;
export type AppProps = {
  createSseClient?: (options: SseClientOptions) => SseConnection;
  scenarioApi?: ScenarioApi;
  executionApi?: ExecutionApi;
};

const defaultCreateSseClient = (options: SseClientOptions): SseConnection =>
  new SseClient(options);
const defaultScenarioApi = createScenarioApi();
const defaultExecutionApi = createExecutionApi();

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
  executionApi = defaultExecutionApi,
}: AppProps) {
  const [connection, setConnection] = useState<ConnectionState>("connecting");
  const [execution, setExecution] = useState<ExecutionState>("idle");
  const [currentCommand, setCurrentCommand] = useState<string>();
  const [scenarios, setScenarios] = useState<ScenarioSummary[]>([]);
  const [selected, setSelected] = useState<ScenarioSummary>();
  const [validation, setValidation] = useState<ScenarioValidation>();
  const [waveTarget, setWaveTarget] = useState<number | "all">();
  const [runningTarget, setRunningTarget] = useState<string>();
  const selectionRequest = useRef(0);
  const [scenarioStatus, setScenarioStatus] = useState<
    "loading" | "ready" | "empty" | "error"
  >("loading");
  const [scenarioError, setScenarioError] = useState<string>();
  const [controlPending, setControlPending] = useState(false);
  const [controlError, setControlError] = useState<string>();
  const [progress, setProgress] = useState<ScenarioProgress>();
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const appendLog = useCallback(
    (entry: LogEntry) => setLogs((current) => [...current.slice(-199), entry]),
    [],
  );
  const [engine] = useState(
    () =>
      new ScenarioEngine({
        submit: executionApi.submit,
        complete: async () => {
          const snapshot = await executionApi.complete();
          setExecution(snapshot.state);
        },
        onProgress: (next) => {
          setProgress(next);
          if (next.error) {
            setControlError(next.error);
            setExecution("error");
          }
        },
      }),
  );

  useEffect(() => {
    const client = createSseClient({
      url: "/api/events",
      onStateChange: (state) => {
        setConnection(state);
        appendLog(connectionEntry(state));
      },
      onEvent: (event) => {
        const logEntry = entryFromSse(event);
        if (logEntry) appendLog(logEntry);
        engine.handleEvent(event);
        const nextState = executionStateFrom(event);
        if (nextState) {
          setExecution(nextState);
          engine.setPaused(nextState === "pausing" || nextState === "paused");
          if (["stopping", "stopped", "emergency_stopping"].includes(nextState))
            engine.cancel();
        }
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
    return () => {
      engine.cancel();
      client.close();
    };
  }, [appendLog, createSseClient, engine]);

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

  useEffect(() => {
    if (connection !== "active") return;
    let active = true;
    executionApi
      .status()
      .then((snapshot) => {
        if (active) setExecution(snapshot.state);
      })
      .catch(() => {
        if (active) setControlError("実行状態を取得できませんでした");
      });
    return () => {
      active = false;
    };
  }, [connection, executionApi]);

  const selectScenario = async (summary: ScenarioSummary) => {
    const request = ++selectionRequest.current;
    setSelected(summary);
    setValidation(undefined);
    setWaveTarget(undefined);
    setProgress(undefined);
    setScenarioError(undefined);
    try {
      const detail = await scenarioApi.get(summary.id);
      if (request !== selectionRequest.current) return;
      setValidation(validateScenario(detail.content));
      appendLog(
        localEntry(
          "scenario.selected",
          `操作手順「${summary.displayName}」を選択しました。`,
          "info",
          { scenarioId: summary.id },
        ),
      );
    } catch (error) {
      if (request !== selectionRequest.current) return;
      appendLog(
        localEntry(
          "scenario.load_failed",
          "操作手順を読み込めませんでした。",
          "error",
          error instanceof Error ? error.message : String(error),
        ),
      );
      setScenarioError(
        error instanceof Error
          ? error.message
          : "操作手順を読み込めませんでした",
      );
    }
  };

  const inactive = connection !== "active";
  const activeExecution = [
    "running",
    "pausing",
    "paused",
    "stopping",
    "emergency_stopping",
  ].includes(execution);
  const canStart =
    !inactive &&
    !controlPending &&
    validation?.valid === true &&
    waveTarget !== undefined &&
    ["idle", "stopped", "completed"].includes(execution);
  const runControl = async (action: ExecutionAction) => {
    setControlPending(true);
    setControlError(undefined);
    try {
      const snapshot = await executionApi.act(action);
      setExecution(snapshot.state);
      if (action === "start" && validation?.valid && waveTarget !== undefined) {
        const label =
          waveTarget === "all" ? "全wave" : `wave ${waveTarget + 1}`;
        setRunningTarget(label);
        setProgress(undefined);
        engine.start(
          validation.scenario,
          waveTarget === "all" ? null : waveTarget,
        );
      }
      if (action === "pause") engine.setPaused(true);
      if (action === "resume") engine.setPaused(false);
      if (action === "stop" || action === "emergency-stop") engine.cancel();
    } catch (error) {
      setControlError(
        error instanceof Error ? error.message : "実行操作に失敗しました",
      );
    } finally {
      setControlPending(false);
    }
  };
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
        <button
          className="emergency-button"
          type="button"
          disabled={
            inactive || controlPending || execution === "emergency_stopping"
          }
          onClick={() => void runControl("emergency-stop")}
        >
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
          <span className="coming-soon">
            {controlPending ? "操作中" : executionLabels[execution]}
          </span>
        </div>
        <div className="control-grid">
          <button
            type="button"
            disabled={!canStart}
            onClick={() => void runControl("start")}
          >
            開始
          </button>
          <button
            type="button"
            disabled={inactive || controlPending || execution !== "running"}
            onClick={() => void runControl("pause")}
          >
            一時停止
          </button>
          <button
            type="button"
            disabled={
              inactive ||
              controlPending ||
              !["paused", "pausing"].includes(execution)
            }
            onClick={() => void runControl("resume")}
          >
            再開
          </button>
          <button
            type="button"
            disabled={
              inactive ||
              controlPending ||
              !["running", "paused", "pausing"].includes(execution)
            }
            onClick={() => void runControl("stop")}
          >
            通常停止
          </button>
        </div>
        {selected && validation?.valid && (
          <fieldset
            className="wave-target"
            disabled={activeExecution || controlPending}
          >
            <legend>実行対象</legend>
            <label>
              <input
                type="radio"
                name="wave-target"
                checked={waveTarget === "all"}
                onChange={() => setWaveTarget("all")}
              />
              全wave（{validation.scenario.commands.flat().length}命令）
            </label>
            {validation.scenario.commands.map((group, index) => (
              <label key={index}>
                <input
                  type="radio"
                  name="wave-target"
                  checked={waveTarget === index}
                  onChange={() => setWaveTarget(index)}
                />
                wave {index + 1}（グループ {index + 1}・{group.length}命令）
              </label>
            ))}
          </fieldset>
        )}
        {selected && validation?.valid && (
          <p className="execution-target" role="status">
            開始対象:{" "}
            {waveTarget === undefined
              ? "未確認"
              : waveTarget === "all"
                ? "全wave"
                : `wave ${waveTarget + 1}`}
          </p>
        )}
        {controlError && (
          <p className="scenario-error" role="alert">
            {controlError}
          </p>
        )}
        {progress && (
          <p className="execution-progress" role="status">
            {progress.error
              ? `停止: ${progress.error}`
              : progress.completedCount === progress.totalCount
                ? `${runningTarget}: ${progress.totalCount}件の命令を完了しました`
                : `${runningTarget}: ${progress.completedCount}/${progress.totalCount}件完了・wave ${progress.groupIndex + 1} 命令${progress.commandIndex + 1}（${progress.waiting ? "完了通知待ち" : "処理中"}）`}
          </p>
        )}
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
                disabled={activeExecution || controlPending}
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
                  wave {index + 1} / グループ {index + 1}（{group.length}命令）
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
        <summary>
          <span>ログと詳細</span>（{logs.length}件）
        </summary>
        {logs.length === 0 ? (
          <p className="empty-state">表示できるログはまだありません。</p>
        ) : (
          <ol className="event-log" aria-label="実行ログ">
            {[...logs].reverse().map((entry) => (
              <li
                className={`event-log__item event-log__item--${entry.severity}`}
                key={entry.id}
              >
                <div className="event-log__heading">
                  <time dateTime={entry.occurredAt}>
                    {new Date(entry.occurredAt).toLocaleTimeString("ja-JP")}
                  </time>
                  <span>{entry.severity.toUpperCase()}</span>
                </div>
                <p>{entry.message}</p>
                <code>
                  {entry.eventType}
                  {entry.commandId ? ` / ${entry.commandId}` : ""}
                </code>
                {entry.detail !== undefined && (
                  <details>
                    <summary>開発者向け詳細</summary>
                    <pre>{JSON.stringify(entry.detail, null, 2)}</pre>
                  </details>
                )}
              </li>
            ))}
          </ol>
        )}
      </details>
    </main>
  );
}
