import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
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
const executionIcons: Record<ExecutionState, string> = {
  idle: "◷",
  running: "▶",
  pausing: "⏳",
  paused: "⏸",
  stopping: "■",
  stopped: "■",
  completed: "✓",
  error: "!",
  emergency_stopping: "!",
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
  const [runningTarget, setRunningTarget] = useState<string>();
  const [runningWaveTarget, setRunningWaveTarget] = useState<number | "all">();
  const [expandedDetails, setExpandedDetails] = useState<Set<number | "all">>(
    () => new Set(),
  );
  const selectionRequest = useRef(0);
  const appRoot = useRef<HTMLElement>(null);
  const [scenarioStatus, setScenarioStatus] = useState<
    "loading" | "ready" | "empty" | "error"
  >("loading");
  const [scenarioError, setScenarioError] = useState<string>();
  const [controlPending, setControlPending] = useState(false);
  const [controlError, setControlError] = useState<string>();
  const [progress, setProgress] = useState<ScenarioProgress>();
  useLayoutEffect(() => {
    if (
      !progress ||
      progress.error ||
      progress.completedCount >= progress.totalCount
    )
      return;
    const currentItems = appRoot.current?.querySelectorAll<HTMLElement>(
      '.command-detail [aria-current="step"]',
    );
    currentItems?.forEach((item) => {
      const detail = item.closest<HTMLElement>(".command-detail");
      if (!detail) return;
      const itemBounds = item.getBoundingClientRect();
      const detailBounds = detail.getBoundingClientRect();
      if (itemBounds.top < detailBounds.top) {
        detail.scrollTop -= detailBounds.top - itemBounds.top + 4;
      } else if (itemBounds.bottom > detailBounds.bottom) {
        detail.scrollTop += itemBounds.bottom - detailBounds.bottom + 4;
      }
    });
  }, [progress, expandedDetails, execution]);
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
    setProgress(undefined);
    setRunningWaveTarget(undefined);
    setExpandedDetails(new Set());
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

  const closeControl = () => {
    if (activeExecution || controlPending) return;
    ++selectionRequest.current;
    setSelected(undefined);
    setValidation(undefined);
    setProgress(undefined);
    setRunningWaveTarget(undefined);
    setExpandedDetails(new Set());
    setRunningTarget(undefined);
    setScenarioError(undefined);
    setControlError(undefined);
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
    ["idle", "stopped", "completed"].includes(execution);
  const activeRunTarget = ["running", "pausing", "paused"].includes(execution)
    ? runningWaveTarget
    : undefined;
  const completedForWave = (index: number): number => {
    if (!progress || !validation?.valid) return 0;
    const groups = validation.scenario.commands;
    if (runningWaveTarget === index) return progress.completedCount;
    if (runningWaveTarget !== "all") return 0;
    const before = groups
      .slice(0, index)
      .reduce((count, group) => count + group.length, 0);
    return Math.max(
      0,
      Math.min(groups[index].length, progress.completedCount - before),
    );
  };
  const toggleDetails = (target: number | "all") => {
    setExpandedDetails((current) => {
      const next = new Set(current);
      if (next.has(target)) next.delete(target);
      else next.add(target);
      return next;
    });
  };
  const commandDetails = (target: number | "all") => {
    if (!validation?.valid || !expandedDetails.has(target)) return null;
    const groups = validation.scenario.commandSources;
    return (
      <div
        className="command-detail"
        id={`command-details-${target}`}
        role="region"
        aria-label={`${target === "all" ? "All" : `Wave${target + 1}`}の命令詳細`}
      >
        {groups.map((group, groupIndex) =>
          target === "all" || target === groupIndex ? (
            <div key={groupIndex}>
              {target === "all" && <h3>Wave{groupIndex + 1}</h3>}
              <ol>
                {group.map((command, commandIndex) => {
                  const current =
                    ["running", "pausing", "paused"].includes(execution) &&
                    progress &&
                    !progress.error &&
                    progress.completedCount < progress.totalCount &&
                    progress.groupIndex === groupIndex &&
                    progress.commandIndex === commandIndex;
                  return (
                    <li
                      key={commandIndex}
                      className={
                        current ? "command-detail__current" : undefined
                      }
                      aria-current={current ? "step" : undefined}
                    >
                      {command}
                    </li>
                  );
                })}
              </ol>
            </div>
          ) : null,
        )}
      </div>
    );
  };
  const controlPendingRef = useRef(false);
  const runControl = async (
    action: ExecutionAction,
    target?: number | "all",
  ) => {
    if (controlPendingRef.current) return;
    if (action === "start" && (!canStart || target === undefined)) return;
    controlPendingRef.current = true;
    setControlPending(true);
    setControlError(undefined);
    try {
      const snapshot = await executionApi.act(action);
      setExecution(snapshot.state);
      if (action === "start" && validation?.valid && target !== undefined) {
        const label = target === "all" ? "全wave" : `wave ${target + 1}`;
        setRunningTarget(label);
        setRunningWaveTarget(target);
        setProgress(undefined);
        engine.start(validation.scenario, target === "all" ? null : target);
      }
      if (action === "pause") engine.setPaused(true);
      if (action === "resume") engine.setPaused(false);
      if (action === "stop" || action === "emergency-stop") engine.cancel();
    } catch (error) {
      setControlError(
        error instanceof Error ? error.message : "実行操作に失敗しました",
      );
    } finally {
      controlPendingRef.current = false;
      setControlPending(false);
    }
  };
  return (
    <main className="app-shell" ref={appRoot}>
      <header className="app-header">
        <div>
          <p className="eyebrow">AUTO PLAY CONSOLE</p>
          <h1>autoFgo</h1>
        </div>
        <div className="status-signals">
          <span
            className={`status-dot status-dot--${connection}`}
            role="img"
            aria-label={`バックエンド：${connectionLabels[connection]}`}
            title={`バックエンド：${connectionLabels[connection]}`}
          />
          <span
            className={`execution-icon execution-icon--${execution}`}
            role="img"
            aria-label={`実行状態：${executionLabels[execution]}`}
            title={`実行状態：${executionLabels[execution]}`}
          >
            {executionIcons[execution]}
          </span>
        </div>
      </header>

      <section className="sticky-status" aria-label="現在の状態">
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

      {selected && (
        <section className="panel" aria-labelledby="controls-title">
          <div className="section-heading">
            <div className="section-title">
              <p className="section-number">02</p>
              <h2 id="controls-title">Control</h2>
            </div>
            <button
              className="close-control"
              type="button"
              aria-label="Controlを閉じる"
              disabled={activeExecution || controlPending}
              onClick={closeControl}
            >
              ×
            </button>
          </div>
          {validation?.valid && (
            <div className="wave-actions" aria-label="実行するwave">
              <div className="wave-action">
                <div className="wave-action__buttons">
                  <button
                    className={
                      activeRunTarget === "all"
                        ? "wave-action__active"
                        : undefined
                    }
                    type="button"
                    disabled={!canStart}
                    onClick={() => void runControl("start", "all")}
                  >
                    All({progress?.completedCount ?? 0}/
                    {validation.scenario.commands.flat().length})
                  </button>
                  <button
                    type="button"
                    className="wave-action__details-button"
                    aria-label="Allの命令を見る"
                    title="Allの命令を見る"
                    aria-expanded={expandedDetails.has("all")}
                    aria-controls="command-details-all"
                    onClick={() => toggleDetails("all")}
                  >
                    <span aria-hidden="true">☷</span>
                  </button>
                </div>
                {commandDetails("all")}
              </div>
              {validation.scenario.commands.map((group, index) => (
                <div className="wave-action" key={index}>
                  <div className="wave-action__buttons">
                    <button
                      className={
                        activeRunTarget === index
                          ? "wave-action__active"
                          : undefined
                      }
                      type="button"
                      disabled={!canStart}
                      onClick={() => void runControl("start", index)}
                    >
                      Wave{index + 1}({completedForWave(index)}/{group.length})
                    </button>
                    <button
                      type="button"
                      className="wave-action__details-button"
                      aria-label={`Wave${index + 1}の命令を見る`}
                      title={`Wave${index + 1}の命令を見る`}
                      aria-expanded={expandedDetails.has(index)}
                      aria-controls={`command-details-${index}`}
                      onClick={() => toggleDetails(index)}
                    >
                      <span aria-hidden="true">☷</span>
                    </button>
                  </div>
                  {commandDetails(index)}
                </div>
              ))}
            </div>
          )}
          <div className="control-grid">
            <button
              className="icon-control"
              type="button"
              aria-label="一時停止"
              title="一時停止"
              disabled={inactive || controlPending || execution !== "running"}
              onClick={() => void runControl("pause")}
            >
              <span aria-hidden="true">⏸</span>
            </button>
            <button
              className="icon-control"
              type="button"
              aria-label="再開"
              title="再開"
              disabled={
                inactive ||
                controlPending ||
                !["paused", "pausing"].includes(execution)
              }
              onClick={() => void runControl("resume")}
            >
              <span aria-hidden="true">▶</span>
            </button>
            <button
              className="icon-control"
              type="button"
              aria-label="通常停止"
              title="通常停止"
              disabled={
                inactive ||
                controlPending ||
                !["running", "paused", "pausing"].includes(execution)
              }
              onClick={() => void runControl("stop")}
            >
              <span aria-hidden="true">■</span>
            </button>
          </div>
          {controlError && (
            <p className="scenario-error" role="alert">
              {controlError}
            </p>
          )}
          {progress && (
            <p className="execution-progress" role="status" aria-live="polite">
              {progress.error
                ? `停止: ${progress.error}`
                : progress.completedCount === progress.totalCount
                  ? `${runningTarget}: ${progress.totalCount}件の命令を完了しました`
                  : `${runningTarget}: ${progress.completedCount}/${progress.totalCount}件完了・wave ${progress.groupIndex + 1} 命令${progress.commandIndex + 1}（${progress.waiting ? "完了通知待ち" : "処理中"}）`}
            </p>
          )}
        </section>
      )}

      <section className="panel" aria-labelledby="scenario-title">
        <div className="section-heading">
          <div className="section-title">
            <p className="section-number">01</p>
            <h2 id="scenario-title">Stages</h2>
          </div>
          {!selected && <span className="coming-soon">未選択</span>}
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
        {scenarioStatus === "ready" && !selected && (
          <div className="scenario-list" aria-label="操作手順一覧">
            {scenarios.map((scenario) => (
              <button
                className="scenario-item"
                key={scenario.id}
                type="button"
                title={scenario.displayName}
                disabled={activeExecution || controlPending}
                onClick={() => void selectScenario(scenario)}
              >
                <span>{scenario.displayName}</span>
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
                <dd className="scenario-members">
                  {validation.scenario.members.map((member, index) => (
                    <span key={index}>{member}</span>
                  ))}
                </dd>
              </div>
            </dl>
            <p className="validation-ok" role="status">
              <span aria-hidden="true">✓</span> 実行可能
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
