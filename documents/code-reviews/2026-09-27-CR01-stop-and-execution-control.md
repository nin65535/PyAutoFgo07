# CR01 コードレビュー — 停止と実行制御

- 実施日: 2026-09-27
- 対象: CR01「停止と実行制御」
- 状態: レビュー完了。修正は別作業。
- 開始時のブランチ: `main`（`origin/main` と同じ位置）
- 基準コミット: `7dc523d6444506384641785322032ba4ebea41bb`
- 開始時の作業ツリー: クリーン

## 確認範囲

指令受付と単一ワーカー、通常停止・緊急停止・一時停止、画面操作のキャンセル確認点、専用ChromeとSSEの監視、フロントエンドのタイムアウトと停止操作を追跡した。`documents/design/command-queue-and-execution-state.md`、`emergency-shutdown.md`、`execution-controls.md`、`sse-events-and-liveness.md`、`scenario-execution-engine.md`、`local-app-lifecycle-pattern.md`、`documents/roadmap.md`、`documents/work-details.md`、`documents/operations.md` と照合した。

## 確認できた指摘

### 1. 高: 停止後にクリックが発生し得る

- 箇所: `backend/src/autofgo/screen_operations.py:202-207`、`209-214`。停止要求側は `backend/src/autofgo/execution.py:226-260`。
- 成立条件: `ScreenOperator._begin()` のキャンセル確認後、`_backend.click()` または `_backend.press()` の直前に別スレッドから停止が届く。操作と停止は同じロックで直列化されていない。
- 再現: 偽の `clock` で `_begin()` 内の時刻取得時に `manager.stop()` を呼び、偽バックエンドのクリックを記録した。結果は `clicks_after_stop=[(10, 10)]`。続く `_finish()` はキャンセルを検出したが、入力は既に発生していた。
- 影響: 通常停止または緊急停止の受付後に、最大で進行中の画面入力が発生する。カード選択など、ゲーム状態を変える入力でも同じ経路を通る。
- 修正案: 停止要求と入力開始を同じ操作ゲートで調停し、停止の完了を返す前に進行中の入力を収束させる。クリックとキー入力の双方で、停止と同時に競合する回帰テストを追加する。

### 2. 中: 画面操作のキャンセルが指令失敗に変わり、停止状態が `error` で上書きされる

- 箇所: `backend/src/autofgo/screen_operations.py:226-238`、`backend/src/autofgo/execution.py:276-330`。
- 成立条件: 撮影・画像探索・クリックなどの操作中に停止し、`OperationCancelledError` がハンドラーから上がる。ワーカーは `CommandCancelledError` だけを取消として扱い、前者を汎用例外として処理する。
- 再現: 偽バックエンドの撮影を停止要求まで待たせた。通常停止、緊急停止のいずれも最終結果は `execution=error, command=failed, error=OperationCancelledError` だった。
- 影響: 正常な停止操作が失敗として表示される。通常停止後は `stopped` に到達せず、再開始も受け付けられない。緊急停止の理由と状態も上書きされる。
- 修正案: 操作キャンセル例外を指令取消へ変換するか、ワーカー境界で取消例外として捕捉する。停止中に通常の失敗が発生しても、緊急停止状態を上書きしない遷移規則を設ける。

### 3. 中: 画面の「緊急停止」は共通の緊急終了処理を通らない

- 箇所: `backend/src/autofgo/commands.py:249-252`、`backend/src/autofgo/shutdown.py:44-57`、`backend/src/autofgo/__main__.py:55-85`。
- 成立条件: 画面の緊急停止ボタンから `POST /api/commands/emergency-stop` を呼ぶ。この経路は `ExecutionManager.emergency_stop()` だけを実行する。Chrome終了・SSE切断時には `EmergencyShutdown.trigger()` を実行する。
- 影響: 手動の緊急停止では入力解放、Uvicorn終了、Chrome終了が行われず、`emergency_stopping` のままプロセスが残る。押下中の入力が実際に残るかは実画面では再現していないが、設計文書の緊急停止手順を満たさない。
- 修正案: APIからも共通の緊急終了処理を起動し、必要な応答を返した後にサーバーと専用Chromeを終了する。入力解放と終了要求を検証するAPI回帰テストを加える。

### 4. 中: SSE接続が複数ある場合、1本の切断で全体が緊急終了する

- 箇所: `backend/src/autofgo/events.py:92-117`、`backend/src/autofgo/__main__.py:48-53,71-84`。
- 成立条件: 同じセッションで2本のSSEストリームが接続され、そのうち1本だけが閉じる。接続監視は購読者数を見ずに `disconnected` を通知する。
- 再現: `EventBroker` に2本接続して片方を閉じると、監視通知は `['connected', 'connected', 'disconnected']` となり、購読者が1本残っていた。起動処理はこの通知で `connection_lost` を立てる。
- 影響: 別タブや画面の再読み込みなどで一方が切断されると、操作中の主画面も強制終了する。
- 修正案: 管理対象の画面接続を1本に限定するか、購読者数が0になったときだけ切断扱いにする。複数接続と片側切断の回帰テストを加える。

## 実画面では未再現の懸念

### 高: フロントエンドの90秒タイムアウト後もバックエンド指令が続く

- 箇所: `frontend/src/execution/scenarioEngine.ts:155-173`、`frontend/src/App.tsx:163-177,563-599`、`backend/src/autofgo/game_automation.py:264-269`。
- 成立条件: 画像処理やOSの画面操作などで1命令が90秒を超える。タイマーは画面側の `fail()` だけを呼び、停止APIを送らない。画面状態は `error` になり、通常停止ボタンも無効化される。バックエンドのキャンセルイベントは立たず、後続のクリックまで進める。
- 影響: 画面が「タイムアウト」と表示した後もゲーム操作が続き得る。実時間の90秒超過と実画面クリックは今回実行していない。
- 修正案: タイムアウト時にバックエンドへ停止を要求し、その結果を同期する。停止が確認できるまで通常停止または緊急停止を操作できるようにする。遅い指令を使った回帰テストを加える。

## 検証結果と制約

- `npm run test:frontend`: 成功（7ファイル、64テスト）。
- `.\.venv\Scripts\python.exe -m pytest backend/tests -q`: 成功（146テスト）。Starlette/httpx関連の非推奨警告2件。
- `npm run lint`: 成功。
- `npm run format:check`: 成功。
- `npm --prefix frontend run build`: 成功。
- 最初のサンドボックス内実行ではpytestの一時ディレクトリへのアクセスとViteの子プロセス起動が拒否された。権限のある実行で再確認して成功し、レビュー時に作成した一時ディレクトリは削除した。
- 実際のChrome終了、SSEのブラウザー切断、LDPlayerへのOS入力は行っていない。上記の再現は代替バックエンドとイベントストリームを使ったもの。
- 旧アプリには変更を加えていない。アプリの修正は本レビューでは行っていない。

## 次の項目

CR02「カード認識とデータ」。CR01の修正は指摘ごとに回帰テストを加える別作業で計画する。

## 2026-09-27 高重大度指摘の修正

- 指摘1: 修正済み。`ExecutionManager` と本番の `ScreenOperator` が同じ入力ゲートを使用し、停止のキャンセル確定とクリック・キー入力の開始を直列化した。停止状態の通知は、入力ゲートでキャンセルが確定した後に送る。入力開始前の停止と、入力中の停止待機を回帰テストで確認した。既に始まったOS入力は途中で中断できないため、停止はその入力呼び出しが戻ってから確定する。
- 90秒タイムアウト: 修正済み。`ScenarioEngine` がタイムアウト時に通常停止APIを呼び、後続指令を送らない。停止要求の成否を画面に表示する。画面側のエラー表示だけでバックエンドの実行状態を `error` に変えないため、停止要求が失敗してもバックエンドが `running` のままなら通常停止と緊急停止を操作できる。タイムアウト中の一時停止、停止API失敗、後続指令の抑止を回帰テストで確認した。
- 指摘2〜4（中）: この時点では保留。後述の修正で対応した。

### 修正後の検証

- `npm run test:frontend`: 成功（7ファイル、65テスト）。
- `.\.venv\Scripts\python.exe -m pytest backend/tests -q`: 成功（150テスト）。Starlette/httpx関連の非推奨警告2件。
- `npm run lint`、`npm run format:check`、`npm --prefix frontend run build`: 成功。
- `git diff --check`: 成功。
- 実際のChromeとLDPlayerを使った停止試験は行っていない。

## 2026-09-27 中重大度指摘の修正

- 指摘2: 修正済み。停止が先に確定した後で画面操作の取消例外や通常の例外が届いても、実行中指令を `cancelled` として確定し、`stopping` から `stopped` への遷移または `emergency_stopping` を維持する。停止前に単独で発生した画面操作の取消例外は従来どおり失敗として扱う。撮影中の通常・緊急停止、緊急停止と通常例外の競合、停止後の再開始を回帰テストで確認した。
- 指摘3: 修正済み。専用Chromeを起動する入口で共通の `EmergencyShutdown` を指令APIへ登録し、画面の緊急停止から入力解放とUvicorn終了要求を実行する。サーバー終了を検知した起動処理が専用Chromeを終了する。APIの応答、処理の冪等性、Chrome終了までを代替サーバー・プロセスで確認した。
- 指摘4: 修正済み。SSE接続監視は購読者数が0から1、1から0へ変わる時だけ通知する。2本の接続のうち1本を閉じても切断通知を出さず、残る接続が配信を受け続けることを確認した。

### 修正後の検証

- `.\.venv\Scripts\python.exe -m pytest backend/tests -q`: 成功（174テスト）。Starlette/httpx関連の非推奨警告2件。既定Tempおよび最初の作業領域内一時ディレクトリは実行環境の権限制約で拒否されたため、権限のある実行と専用一時ディレクトリで再確認し、作業後に削除した。
- `.\.venv\Scripts\python.exe -m ruff check backend`、`.\.venv\Scripts\python.exe -m ruff format --check backend`、`git diff --check`: 成功。
- 実際のChrome終了とLDPlayerへの入力解放は行っていない。
