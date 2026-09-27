# CR03 コードレビュー — フロントエンドとAPI

- 実施日: 2026-09-27
- 対象: CR03「フロントエンドとAPI」
- 状態: レビュー完了。高重大度の指摘1・2は末尾の追記で修正済み。中3件・低1件は未修正。
- 開始時のブランチ: `main`（`origin/main` と同じ位置）
- 基準コミット: `e0424b1d79ee08b75912883a42834cfa0614945c`
- 開始時の作業ツリー: クリーン

## 確認範囲

All/Waveの実行列、命令IDとSSE終端イベントによる重複防止、画面とAPIの実行状態同期、Spaceによる一時停止と通常・緊急停止の操作可否、セッショントークンとOrigin検証、API入力制限、失敗表示を追跡した。`documents/roadmap.md`、`documents/work-details.md`、`documents/operations.md` と、設計資料 `scenario-execution-engine.md`、`r20-wave-and-compact-ui.md`、`connection-security-and-input-validation.md`、`sse-events-and-liveness.md`、`data-model-and-command-spec.md`、`logging-and-error-display.md` を照合した。

同じ命令IDの再送はバックエンドが重複として返し、フロントエンドは待機中の命令IDと一致する終端イベントだけで次へ進む。通常のAll/Wave操作では対象Waveの命令だけが送られる。一方、以下の経路に問題がある。

Spaceキーは、マウスを使えない緊急時に即時に操作を止めるための、再開可能な一時停止として意図されている。実装もバックエンドから `pause()` を呼び、指令破棄とアプリ終了を行うAPIの「緊急停止」とは役割が異なる。

## 確認できた指摘

### 1. 高: ローカルURLの検証を外部ホストが通過し、起動トークンが渡る

- 箇所: `backend/src/autofgo/config.py:51-52`、`backend/src/autofgo/browser.py:173-185`、`backend/src/autofgo/main.py:24-32`、`backend/src/autofgo/security.py:46-52`。
- 成立条件: `AUTOFGO_CHROME_APP_URL` に `http://localhost.attacker.invalid:5173` のような、文字列では `http://localhost` で始まる外部ホストを設定する。設定は `startswith` だけで通る。Chrome起動URLにはセッショントークンのフラグメントが付き、APIの許可Originもこの外部ホストになる。
- 再現: `.venv` のPythonで `Settings(chrome_app_url="http://localhost.attacker.invalid:5173")` を生成でき、`urlsplit(...).hostname` は `localhost.attacker.invalid`、`origin_from_url(...)` は同じ外部Originになった。外部サイトへの実際の接続とトークン流出は行っていない。
- 影響: この設定で起動すると外部サイトのJavaScriptがURLフラグメントを読み取れ、セッション資格情報を使ってローカルAPIの自動操作を要求できる。設定ミスや設定値の改ざんが必要だが、ローカル接続に限定する設計上の境界を破る。
- 修正案: URLを解析し、スキーム、`hostname`、ポート、ユーザー情報、パスなどを個別に検証する。許可ホストは `localhost`、`127.0.0.1`、`::1` に限定し、外部ホストへ見える接頭辞やユーザー情報を使った偽装を拒否する回帰テストを追加する。

### 2. 高: 指令受付後にHTTP応答を失うと、画面の停止表示後も指令が続く

- 箇所: `frontend/src/execution/scenarioEngine.ts:148-155`、`172-176`、`frontend/src/App.tsx:175-179,611-618`、受付後に動作するバックエンドは `backend/src/autofgo/execution.py:118-135`。
- 成立条件: `POST /api/commands` はバックエンドで受理されたが、応答だけが失われるかフロントエンド側で送信失敗として扱われる。`dispatch()` は画面の進行を失敗にするだけで停止APIを呼ばない。
- 再現: 送信Promiseを拒否させた隔離テストで、進行にはエラーが記録されたが `stop` の呼び出しは0件だった。受付後の応答喪失そのものは実ネットワークで再現していない。
- 影響: 画面に「停止」と表示され、後続命令は送られない一方、受理済みの現在の命令はクリックなどを続け得る。命令終了後もバックエンドは `running` のまま残る。
- 修正案: 送信結果が不明な場合は同じ命令IDで受付結果を照会または安全に再送して状態を確定し、継続できないときは停止要求と結果同期を行う。受付後に応答だけを落とす回帰テストを追加する。

### 3. 中: 遅い操作API応答が新しいSSE状態を巻き戻す

- 箇所: `frontend/src/App.tsx:191-201`、`390-413`。初回の状態取得も `244-258`。
- 成立条件: 通常停止APIの応答に `stopping` が含まれ、先にSSEで `stopped` が届いた後、古い応答が画面へ到着する。両方が順序検証なしに `setExecution` を呼ぶ。
- 再現: 停止APIのPromiseを保留し、SSEの `stopped` を渡してから `stopping` 応答を返す隔離UIテストで、表示は「停止処理中」に戻り、All開始ボタンも無効のままだった。
- 影響: バックエンドでは停止が完了していても画面は停止処理中に固定され、再実行できない。同じ競合は初回status取得や他の操作応答でも成立する。
- 修正案: SSEとAPI応答に共通の状態世代番号を持たせ、古いスナップショットを適用しない。最低限、操作応答後に最新statusを取得して照合する。SSE先着の回帰テストを追加する。

### 4. 中: 一時停止後の再実行で指令タイムアウト監視が復帰しない場合がある

- 箇所: `frontend/src/execution/scenarioEngine.ts:47-48`、`109-124`、`143-149`、`frontend/src/App.tsx:195-200,408-412`。
- 成立条件: 一時停止で `ScenarioEngine.paused` が真になり、通常停止の応答側が先に `engine.cancel()` する。後着の停止SSEは非活性エンジンの `setPaused(false)` で無視される。次の開始時に `running` SSEが `engine.start()` より先に届くと、同様に無視され、`paused` が残る。
- 再現: 隔離エンジンテストで `start → setPaused(true) → cancel → start` とし、タイムアウトを超えて時刻を進めても `stop` は0件だった。上記のUIイベント順序を実ブラウザーでは再現していない。
- 影響: 再実行の指令はバックエンドで進むが、フロントエンドの90秒監視と自動停止が働かない。
- 修正案: `cancel()` または `start()` で一時停止フラグと残り時間を初期化する。停止応答とSSEの両順序で再実行後のタイムアウトを検証する。

### 5. 中: 指令失敗後の `error` 状態から再実行できない

- 箇所: `backend/src/autofgo/execution.py:137-143,288-295`、`frontend/src/App.tsx:319-323`、`backend/src/autofgo/commands.py:215-228`。
- 成立条件: 画像認識や画面操作などで指令ハンドラーが例外を出し、バックエンドが `error` へ移る。開始APIも画面の開始条件も `error` を許可せず、状態を `idle` に戻すAPIもない。
- 影響: 一時的な認識失敗でも、そのプロセスではAll/Waveをやり直せず、アプリを再起動するしかない。設計資料の `error → idle` の再実行準備経路を満たさない。
- 修正案: 実行中の指令とキューがないことを確認した上で `error` から安全に再準備する操作を設ける。失敗後に別のAll/Waveを開始できるAPI・画面の回帰テストを追加する。

### 6. 低: 他の操作APIの応答待ち中は画面の緊急停止ボタンを使えない

- 箇所: `frontend/src/App.tsx:390-399`、`453-459`。別経路のSpace監視は `backend/src/autofgo/space_pause.py:49-65`。
- 成立条件: 開始、一時停止、再開、通常停止のいずれかのAPI呼び出しが応答待ちのままになる。共通の `controlPending` が緊急停止ボタンも無効にし、`runControl` のガードも緊急停止を拒否する。
- 再現: 開始後に一時停止APIのPromiseを保留した隔離UIテストで、緊急停止ボタンが無効になった。5件の隔離再現テストの1件。
- 影響: APIの緊急停止は応答が戻るまで画面から要求できない。一方、実行状態が `running` ならSpaceキーで再開可能な一時停止を要求でき、次の操作確認点以降の入力を抑止する。マウスを使えない緊急場面ではSpaceが意図した操作であり、当初の高重大度評価は過大だった。ボタンの制限はAPI応答待ちという限定条件で残る。
- 修正案: 画面の緊急停止ボタンを通常操作の応答待ちから独立させる。Spaceによる一時停止は維持し、応答待ちの各操作中にボタンのAPI要求が送られることを検証する。

## 仕様として確認した動作

Wave単独実行では選択Waveの命令だけを送信し、カード選択用の `frontMembers` には前段Waveの `swap` を反映する。たとえば初期メンバー `A,B,C,D`、Wave1が `swap(0,3)`、Wave2が `attack_cards('B0')` の場合、Wave2単独で送る `frontMembers` は `D,B,C` となる。隔離テストでもこの値を確認し、ユーザーから期待通りの動作と確認されたため、指摘から除外した。[R20のWave実行仕様](../design/r20-wave-and-compact-ui.md)と[R22のカード指定仕様](../design/r22-attack-card-priority.md)にも明記した。実装は現状維持とする。

## 検証結果と制約

- `npm run test:frontend`: 成功（7ファイル、65テスト）。
- `.\.venv\Scripts\python.exe -m pytest backend/tests -q --basetemp .review-pytest-tmp2 -p no:cacheprovider`: 成功（155テスト）。StarletteとAnyIOの既存非推奨警告2件。
- `npm run lint`、`npm run format:check`、`npm --prefix frontend run build`: 成功。
- `git diff --check`: 成功。
- 隔離した一時的なVitestテスト5件のうち4件で指摘2〜4および6の成立条件を確認し、1件で上記Wave動作を確認した。テストファイルは削除し、アプリ本体・既存テストは変更していない。指摘1は `.venv` のPythonで設定値と解析ホストを確認した。指摘5は状態遷移とAPI・画面の開始条件をコード上で照合した。
- 最初のサンドボックス内実行ではViteの子プロセス起動とpytestの一時フォルダー作成が拒否された。必要な権限で再実行して成功し、検証用フォルダーは削除した。
- 実際のChrome・LDPlayerでのイベント競合、応答喪失、外部サイトへの接続は行っていない。CR01・CR02の既知の未修正指摘は本書では重複して列挙していない。旧アプリには変更を加えていない。

## 次の項目

CR04「起動・運用と横断確認」。CR03の残る指摘3〜6は、条件を回帰テストにしてから別作業で修正する。

## 2026-09-27 高重大度指摘1・2の修正

- 指摘1: 修正済み。`AUTOFGO_CHROME_APP_URL` をURLとして解析し、`http` と正確なループバックホスト名だけを許可する。外部ドメインをローカルホスト名に見せる接頭辞、ユーザー情報、無効なポート、制御文字を拒否する。既存のローカルURLとIPv6ループバックは許可する。
- 指摘2: 修正済み。指令送信でエラーが起きた場合、後続命令の送信を抑止し、バックエンドへ通常停止を要求する。画面では「停止済み」と断定せず送信結果と停止要求を表示する。停止APIの応答も確認できなければ、その状態不明を表示する。
- 設計資料 `connection-security-and-input-validation.md` と `scenario-execution-engine.md` に検証条件と停止時の表示を反映した。
- 中・低重大度の指摘3〜6は今回の修正対象外。

### 修正後の検証

- `.\.venv\Scripts\python.exe -m pytest backend/tests -q --basetemp .review-cr03-pytest-tmp -p no:cacheprovider`: 成功（167テスト）。StarletteとAnyIOの既存非推奨警告2件。
- `npm run test:frontend`: 成功（7ファイル、67テスト）。
- `npm run lint`、`npm run format:check`、`npm --prefix frontend run build`、`git diff --check`: 成功。
- 外部ホストの偽装URLとローカルURLの受理・拒否、指令のHTTP応答喪失後の停止要求、停止APIの失敗表示、画面から停止APIが呼ばれる経路を回帰テストで確認した。
- 実ネットワークでの応答喪失、実際のChrome・LDPlayer操作、外部サイトへの接続は行っていない。停止APIも通信不能な場合、自動停止の成立は保証できず、画面には結果を確認できない旨を表示する。検証用一時フォルダーは削除した。
