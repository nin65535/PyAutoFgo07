# 共通データモデルと命令仕様

## 1. 適用範囲

この文書は、操作手順JSONのスキーマ、文字列命令を解析して得られる型付きコマンド、およびREST APIの共通要求・応答形式を定義する。SSEイベントの詳細は、R02の後続検討で追記する。

旧アプリの操作手順JSONは新アプリへ直接読み込ませない。変換ツールを通して、この文書で定義する新形式へ変換してから使用する。旧JSONおよび旧アプリは変更しない。

## 2. 操作手順JSON

### 2.1 構造

```ts
type Scenario = {
  schemaVersion: 1;
  members: string[];
  commands: string[][];
};
```

有効な操作手順JSONの例を示す。

```json
{
  "schemaVersion": 1,
  "members": ["メンバーA", "メンバーB"],
  "commands": [
    ["skill(0)", "skill(5,2)", "attack(0,1)"],
    ["swap(2,3)", "master_skill(1)", "attack()"]
  ]
}
```

### 2.2 検証規則

| 項目 | 規則 |
| --- | --- |
| ルート | JSONオブジェクトであり、`schemaVersion`、`members`、`commands`を必須とする |
| 未知のプロパティ | ルートを含め、スキーマで定義していないプロパティは拒否する |
| `schemaVersion` | 数値の`1`だけを許可する |
| `members` | 1件以上6件以下の配列とする |
| `members`の要素 | 空文字を拒否し、最大100文字とする。重複は許可する |
| `commands` | 1グループ以上5グループ以下の配列とする |
| 命令グループ | 1命令以上20命令以下の配列とし、空グループを拒否する |
| 命令文字列 | 空文字を拒否し、最大100文字とする |

## 3. 文字列命令

文字列命令はPython式やJavaScript式ではなく、本アプリ専用の限定的な記法である。文字列全体が以下のいずれかの形式へ完全一致する場合だけ受け付ける。

共通規則は次のとおりとする。

- 命令名は小文字の`skill`、`master_skill`、`attack`、`swap`だけを許可する
- 命令文字列内の空白は、前後および引数間を含めて一切許可しない
- 引数はASCIIの10進数字で表した非負整数だけを許可する
- 数値`0`は`0`と記述し、`00`や`01`のような先頭ゼロを許可しない
- 符号、小数、指数表記、文字列、式、コメント、末尾カンマを許可しない

### 3.1 `skill`

```text
skill(skillIndex)
skill(skillIndex,targetIndex)
```

| 引数 | 必須 | 値域 |
| --- | --- | --- |
| `skillIndex` | 必須 | `0`以上`8`以下 |
| `targetIndex` | 任意 | `0`以上`5`以下 |

### 3.2 `master_skill`

```text
master_skill(skillIndex)
master_skill(skillIndex,targetIndex)
```

| 引数 | 必須 | 値域 |
| --- | --- | --- |
| `skillIndex` | 必須 | `0`以上`3`以下 |
| `targetIndex` | 任意 | `0`以上`2`以下 |

### 3.3 `attack`

```text
attack()
attack(noblePhantasmIndex)
attack(noblePhantasmIndex,noblePhantasmIndex)
attack(noblePhantasmIndex,noblePhantasmIndex,noblePhantasmIndex)
```

- 引数は0個以上3個以下とする
- 各引数は`0`以上`2`以下とする
- 同じ値を複数回指定することはできない
- 引数の順序を宝具の選択順として保持する

### 3.4 `swap`

```text
swap(frontIndex,backIndex)
```

| 引数 | 必須 | 値域 |
| --- | --- | --- |
| `frontIndex` | 必須 | `0`以上`2`以下 |
| `backIndex` | 必須 | `3`以上`5`以下 |

## 4. 型付きコマンド

フロントエンドは検証済みの文字列命令を、次の判別可能なユニオン型へ変換する。

```ts
type SkillCommand = {
  type: "skill";
  skillIndex: number;
  targetIndex?: number;
};

type MasterSkillCommand = {
  type: "master_skill";
  skillIndex: number;
  targetIndex?: number;
};

type AttackCommand = {
  type: "attack";
  noblePhantasmIndexes: number[];
};

type SwapCommand = {
  type: "swap";
  frontIndex: number;
  backIndex: number;
};

type ScenarioCommand =
  | SkillCommand
  | MasterSkillCommand
  | AttackCommand
  | SwapCommand;
```

`type`は元の文字列命令名と一致させる。位置を示すプロパティ名には`Index`または`Indexes`を付け、すべて0始まりとする。

変換例を示す。

| 文字列命令 | 型付きコマンド |
| --- | --- |
| `skill(5,2)` | `{"type":"skill","skillIndex":5,"targetIndex":2}` |
| `master_skill(1)` | `{"type":"master_skill","skillIndex":1}` |
| `attack(2,0)` | `{"type":"attack","noblePhantasmIndexes":[2,0]}` |
| `attack()` | `{"type":"attack","noblePhantasmIndexes":[]}` |
| `swap(2,4)` | `{"type":"swap","frontIndex":2,"backIndex":4}` |

指令IDや操作手順内の実行位置などの管理情報は`ScenarioCommand`へ含めず、操作API要求の共通情報として型付きコマンドを包む。

## 5. 識別子

### 5.1 コマンドID

- コマンドIDはUUID v7の文字列とする
- フロントエンドが操作APIへ送信する前に発行する
- 同一操作要求の通信再送では、最初の送信時と同じコマンドIDを使用する
- 利用者または実行エンジンが改めて同じ命令を実行する場合は、新しいコマンドIDを発行する
- コマンドIDはバックエンドの再起動をまたいで一意な識別子として扱う
- バックエンドが同じコマンドIDと同じ要求内容を再受信した場合は、命令を二重実行せず、既存の受付状態または実行結果を返す
- バックエンドが同じコマンドIDと異なる要求内容を受信した場合は、不正な要求として拒否する

### 5.2 イベントID

- イベントIDはバックエンド起動中に単調増加する整数とする
- 最初のイベントIDを`1`とし、バックエンドの再起動後は再び`1`から開始する
- バックエンドがイベントの生成時に発行する
- SSEの`id`フィールドとイベントデータ内の`eventId`には同じ値を格納する
- SSEイベントの再送は行わず、イベント履歴を再送目的でメモリ上に保持しない
- ハートビートにはイベントIDを付与しない

### 5.3 セッションID

- バックエンドを起動するたびに新しいセッションIDを発行する
- セッションIDはUUID v4とする
- 小文字、ハイフン付きの標準的な36文字表記とする
- バックエンド起動時に1回だけ生成し、同じバックエンドプロセスの動作中は変更しない
- セッションIDは永続保存せず、バックエンド再起動時に必ず新しく生成する
- セッションIDは秘密情報ではなく、ログへ記録してよい
- セッショントークンとは別の値として生成する
- イベントIDはセッション内で一意とし、セッションIDとイベントIDの組み合わせによってバックエンド再起動の前後を区別する
- SSEイベントにはセッションIDを含める
- セッションIDの形式が不正な要求は`422 Unprocessable Content`および`VALIDATION_ERROR`で拒否する
- UUID v4として正しいが現在のセッションIDと異なる要求は`409 Conflict`および`SESSION_MISMATCH`で拒否する

セッションIDの形式は次の正規表現に一致するものとする。

```text
^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$
```

### 5.4 接続断

- SSE接続が切断された場合、フロントエンドは再接続を試みない
- バックエンドは3秒間隔でハートビートを送信する
- フロントエンドは、通常イベントまたはハートビートを最後に受信してから10秒間何も受信しなかった場合、接続断と判定して不活性状態にする
- SSEストリームの終了またはSSEエラーを明示的に検出した場合は、10秒を待たず即座に不活性状態にする
- 不活性状態では新しい指令の送信、実行開始、一時停止、再開など、バックエンドを必要とする操作を受け付けない
- 不活性状態から同じ画面のまま復旧する経路は設けない
- バックエンドを再起動した場合は、新しいセッションIDを持つ別の実行セッションとして、バックエンドが起動する新しいフロントエンドを使用する
- ブラウザ標準のSSE自動再接続に依存せず、クライアント側で明示的に接続を終了する

## 6. REST API共通形式

### 6.1 共通規則

- JSONのプロパティ名には`camelCase`を使用する
- リクエストで未知のプロパティを受け取った場合は拒否する
- 値が存在しない任意プロパティは原則として省略し、意味のない`null`を使用しない
- 要求および応答の文字コードはUTF-8とし、JSONでは`Content-Type: application/json; charset=utf-8`を使用する
- 日時はUTCのISO 8601形式とし、ミリ秒精度および末尾の`Z`を使用する。例：`2026-09-20T05:24:31.482Z`
- シナリオ一覧APIにはページングを設けず、全件を返す

### 6.2 セッション情報と認証情報

REST API要求では次のHTTPヘッダーを必須とする。

```http
X-AutoFgo-Session-Id: <session-id>
Authorization: Bearer <token>
```

- `X-AutoFgo-Session-Id`はバックエンドの起動単位を識別するセッションIDを送る
- `Authorization`は起動時に生成されたセッショントークンをBearer認証方式で送る
- セッションIDは識別子であり、認証用の秘密情報として扱わない
- セッショントークンは秘密情報として扱い、ログやユーザー向けエラーへ出力しない
- SSE接続でも同じヘッダーを送信する。ブラウザ標準の`EventSource`は任意ヘッダーを設定できないため、実装時はヘッダーを設定可能で、自動再接続を行わない接続方式を使用する

### 6.3 操作指令要求

操作指令要求は`commandId`と`command`を必須とする。

```json
{
  "commandId": "0195d84e-7c82-7a31-a261-a1db5a3f7190",
  "command": {
    "type": "skill",
    "skillIndex": 5,
    "targetIndex": 2
  }
}
```

### 6.4 成功応答

成功応答は、結果を`data`プロパティへ格納する共通形式とする。

```json
{
  "data": {
    "commandId": "0195d84e-7c82-7a31-a261-a1db5a3f7190",
    "status": "queued",
    "acceptedAt": "2026-09-20T05:24:31.482Z"
  }
}
```

新しい操作指令は、入力検証と受付処理に成功した時点で`202 Accepted`を返す。API応答はキューへの受付完了だけを表し、実行の開始、完了、失敗およびキャンセルはSSEで通知する。

同じコマンドIDかつ同じ要求内容を再受信した場合は命令を二重実行せず、`200 OK`で既存の状態または結果を返す。この場合は`duplicate: true`を含める。同じコマンドIDで異なる要求内容を受信した場合は`409 Conflict`とする。

### 6.5 エラー応答

エラー応答は、エラー情報を`error`プロパティへ格納する共通形式とする。

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "入力値が不正です。",
    "details": {
      "issues": [
        {
          "path": "/command/skillIndex",
          "code": "OUT_OF_RANGE",
          "message": "0以上8以下で指定してください。"
        }
      ]
    }
  }
}
```

- `error.code`と`error.message`を必須とする
- `error.details`は補足情報がある場合だけ含める
- 入力エラーの対象位置はJSON Pointerで表す
- 内部例外、スタックトレース、ローカルファイルパスおよび秘密情報を応答へ含めない
- エラーコードは`UPPER_SNAKE_CASE`の固定値とし、既存コードの意味を変更しない
- `message`は利用者へ表示できる簡潔な日本語とし、フロントエンドの処理分岐には使用しない
- `details`は自由形式にせず、エラーコードごとに定義した型を使用する
- `retryable`および`errorId`は設けない
- 想定外の例外は`INTERNAL_ERROR`へ変換し、生の例外メッセージを応答へ含めない

検証エラーは、検出した問題を`details.issues`へ配列で格納する。

```ts
type ValidationIssueCode =
  | "REQUIRED"
  | "INVALID_TYPE"
  | "UNKNOWN_FIELD"
  | "INVALID_FORMAT"
  | "OUT_OF_RANGE"
  | "TOO_LONG"
  | "DUPLICATE_VALUE"
  | "INVALID_COMBINATION";

type ValidationIssue = {
  path: string;
  code: ValidationIssueCode;
  message: string;
};

type ValidationErrorDetails = {
  issues: ValidationIssue[];
};
```

| 検証詳細コード | 用途 |
| --- | --- |
| `REQUIRED` | 必須項目が存在しない |
| `INVALID_TYPE` | 値の型が異なる |
| `UNKNOWN_FIELD` | 未知のプロパティが存在する |
| `INVALID_FORMAT` | 文字列などの形式が不正 |
| `OUT_OF_RANGE` | 数値または要素数が許容範囲外 |
| `TOO_LONG` | 文字列が長すぎる |
| `DUPLICATE_VALUE` | 重複を禁止した値が複数存在する |
| `INVALID_COMBINATION` | 個々の値は有効だが組み合わせが不正 |

初期エラーコードは次のとおりとする。

| エラーコード | HTTP | 用途 |
| --- | --- | --- |
| `INVALID_JSON` | `400` | API要求のJSON構文が不正 |
| `VALIDATION_ERROR` | `422` | 型、必須項目、値域または形式が不正 |
| `UNAUTHORIZED` | `401` | セッショントークンが存在しない、または不正 |
| `SESSION_MISMATCH` | `409` | セッションIDが現在のバックエンドと異なる |
| `SCENARIO_NOT_FOUND` | `404` | シナリオが存在しない |
| `SCENARIO_READ_FAILED` | `500` | シナリオファイルを読み取れない |
| `SCENARIO_INVALID_JSON` | `422` | シナリオファイルがJSONとして不正 |
| `COMMAND_NOT_FOUND` | `404` | 指定したコマンドが存在しない |
| `COMMAND_ID_CONFLICT` | `409` | 同じコマンドIDで異なる要求内容を受信した |
| `INVALID_STATE` | `409` | 現在の状態では要求を実行できない |
| `QUEUE_FULL` | `429` | 指令キューの受付上限を超えた |
| `COMMAND_TIMEOUT` | SSE | 受付後の指令が制限時間内に完了しなかった |
| `OPERATION_FAILED` | SSE | 受付後の画面操作などに失敗した |
| `SERVICE_UNAVAILABLE` | `503` | 停止処理中などで指令を受け付けられない |
| `INTERNAL_ERROR` | `500`またはSSE | 想定外の内部エラーが発生した |

`COMMAND_TIMEOUT`と`OPERATION_FAILED`は受付後に発生するため、SSEの`command.failed`で通知する。エラーコードはフロントエンドで異なる処理が必要になった時点で追加する。

エラーコードごとの`details`は必要な情報だけを持つ。代表例を示す。

```ts
type CommandIdConflictDetails = {
  commandId: string;
};

type InvalidStateDetails = {
  currentState: string;
  requiredStates?: string[];
};

type CommandTimeoutDetails = {
  timeoutMs: number;
};
```

### 6.6 HTTPステータスコード

| ステータス | 用途 |
| --- | --- |
| `200 OK` | 取得成功、更新成功、または重複した同一コマンドの既存結果返却 |
| `202 Accepted` | 新しい操作指令の受付成功 |
| `400 Bad Request` | JSON構文不正など、要求形式を解釈できない |
| `401 Unauthorized` | セッショントークンが存在しない、または不正 |
| `404 Not Found` | 指定したシナリオまたはリソースが存在しない |
| `409 Conflict` | 同一コマンドIDで内容が異なる、または現在状態と要求が競合する |
| `413 Content Too Large` | リクエストサイズが上限を超えている |
| `422 Unprocessable Content` | JSONは解釈できるが、型、必須項目または値域が不正 |
| `429 Too Many Requests` | 受付数または呼び出し頻度の制限を超えている |
| `500 Internal Server Error` | 想定外の内部エラー |
| `503 Service Unavailable` | 停止処理中または緊急停止中など、一時的に受付不能 |

`400 Bad Request`と`422 Unprocessable Content`は区別する。

## 7. SSEイベント

### 7.1 イベント名

イベント名は小文字の`領域.出来事`を基本とし、領域分けが不要なものは単語だけとする。

| イベント名 | 用途 |
| --- | --- |
| `command.accepted` | 指令を受け付けた |
| `command.started` | 指令の実行を開始した |
| `command.completed` | 指令が正常終了した |
| `command.failed` | 指令がエラー終了した |
| `command.cancelled` | 実行前または実行中の指令を取り消した |
| `execution.state_changed` | アプリケーション全体の実行状態が変わった |
| `warning` | 処理を継続できる警告が発生した |
| `error` | 指令に限定されないエラーが発生した |
| `heartbeat` | 接続の生存を確認する |

### 7.2 通常イベントの共通形式

ハートビート以外の通常イベントは、次の共通形式とする。

```ts
type EventEnvelope<TType extends string, TData> = {
  eventId: number;
  sessionId: string;
  type: TType;
  occurredAt: string;
  commandId?: string;
  data: TData;
};
```

- `eventId`、`sessionId`、`type`、`occurredAt`および`data`を必須とする
- `commandId`は`command.*`イベントで必須とし、それ以外のイベントでは省略する
- `occurredAt`はREST APIと同じUTCのISO 8601形式とする
- SSEの`id`とJSONの`eventId`には同じ値を格納する
- SSEの`event`とJSONの`type`には同じ値を格納する
- 通常イベントのイベントIDは、直前に送信した通常イベントより大きい値とする
- イベントIDの順序と送信順序を一致させる
- 1イベントのデータはUTF-8のJSONとして1つの`data`フィールドで送る

送信例を示す。

```text
id: 42
event: command.completed
data: {"eventId":42,"sessionId":"0195d84e-7c82-7a31-a261-a1db5a3f7190","type":"command.completed","occurredAt":"2026-09-20T05:24:31.482Z","commandId":"0195d850-184c-7901-a7bb-52b10fbc9024","data":{"status":"completed","durationMs":1420}}
```

### 7.3 指令イベント

指令ごとに次の順序を保証する。

```text
command.accepted
    ↓
command.started
    ↓
command.completed | command.failed | command.cancelled
```

- `command.accepted`より前に`command.started`を送らない
- 終端イベントは`command.completed`、`command.failed`、`command.cancelled`のいずれか1つだけとする
- 終端イベントの後に同じ指令の状態を変えるイベントを送らない
- REST APIの受付応答に加えて、受付をイベント系列で追跡できるよう`command.accepted`も送る
- `command.failed`のエラー情報にはREST APIと同じエラー構造を使用する
- 指令固有の失敗は`command.failed`だけで通知し、同じ問題を`error`として重複通知しない

`command.cancelled`のキャンセル理由は、次の4種類に限定する。

| 理由 | 用途 |
| --- | --- |
| `normal_stop` | ユーザー操作または通常フローによって停止した |
| `emergency_stop` | 緊急停止によって取り消した |
| `frontend_disconnected` | フロントエンドとの接続断によって取り消した |
| `execution_failed` | 別の指令が失敗し、後続指令を実行せず取り消した |

```json
{
  "status": "cancelled",
  "reason": "normal_stop"
}
```

一時停止はキャンセルとして扱わない。新しい指令による既存指令の自動的な置き換えは行わない。キャンセル理由は必要になった時点で追加し、追加時にはスキーマバージョンとの互換性を確認する。

`command.completed`の`data`は、現在定義している4命令で共通して次の形式とする。

```ts
type CommandCompletedData = {
  status: "completed";
  durationMs: number;
};
```

```json
{
  "status": "completed",
  "durationMs": 1420
}
```

- `durationMs`は指令の実行開始から完了までの時間を整数ミリ秒で表し、キューでの待機時間を含めない
- `skill`、`master_skill`、`attack`、`swap`では`result`を含めない
- 送信済みの型付きコマンドや内部のクリック座標を完了データへ重複して含めない
- 将来、画像検出など返却データを持つ命令を追加する場合は、その命令に限って命令別の`result`を定義する
- 返却データがない命令では、空の`result`オブジェクトを追加しない

### 7.4 実行状態変更

`execution.state_changed`は、アプリケーション全体の状態が実際に変わった場合だけ送る。同じ状態への更新では送らない。

```json
{
  "previousState": "running",
  "currentState": "stopping",
  "reason": "normal_stop"
}
```

### 7.5 警告とエラー

- `warning`は処理を継続できる問題に使用する
- `error`は特定の指令に限定されないエラーに使用する
- `command.failed`および`error`のエラー情報にはREST APIと同じエラー型を使用する
- どちらも機械判定用の`code`と表示用の`message`を持つ
- 内部例外、スタックトレース、ローカルファイルパスおよび秘密情報を含めない

### 7.6 ハートビート

ハートビートは通常イベントの共通形式とは分け、イベントIDとコマンドIDを付与しない。

```text
event: heartbeat
data: {"type":"heartbeat","sessionId":"0195d84e-7c82-7a31-a261-a1db5a3f7190","sentAt":"2026-09-20T05:24:33.000Z"}
```

```ts
type HeartbeatEvent = {
  type: "heartbeat";
  sessionId: string;
  sentAt: string;
};
```

- `sessionId`と`sentAt`を必須とする
- `sentAt`はUTCのISO 8601形式とする
- 3秒間隔で送信する
- 通常イベントとハートビートのどちらを受信した場合も、フロントエンドの最終受信時刻を更新する

## 8. 状態モデル

接続状態、シナリオ実行状態、個別指令状態は、それぞれ独立した状態として管理する。

### 8.1 接続状態

```ts
type ConnectionState = "connecting" | "connected" | "inactive";
```

| 状態 | 意味 |
| --- | --- |
| `connecting` | 初回SSE接続の確立待ち |
| `connected` | バックエンドと正常に通信中 |
| `inactive` | 接続断が確定し、操作不能 |

許可する遷移は次のとおりとする。

```text
connecting -> connected
connecting -> inactive
connected  -> inactive
```

- 初回接続の明示的な失敗、SSEストリームの終了またはSSEエラーでは即座に`inactive`へ遷移する
- イベントを受信しない状態では、最終受信から10秒経過すると`inactive`へ遷移する
- `inactive`は終端状態とし、同じフロントエンドから再接続しない
- `inactive`ではバックエンドを必要とする操作をすべて無効化する

### 8.2 シナリオ実行状態

```ts
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
```

| 状態 | 意味 |
| --- | --- |
| `idle` | シナリオを開始していない |
| `running` | シナリオを実行中 |
| `pausing` | 一時停止要求を受け、現在の処理が安全な休止地点へ到達するのを待っている |
| `paused` | 現在の処理を休止し、次の処理を開始しない |
| `stopping` | 通常停止処理中 |
| `stopped` | 通常停止が完了した |
| `completed` | 全指令が正常終了した |
| `error` | 指令の失敗または実行継続不能なエラーによって終了した |
| `emergency_stopping` | 緊急停止処理中 |

主要な状態遷移は次のとおりとする。

```text
idle -> running

running -> pausing -> paused -> running
running -> stopping -> stopped
running -> completed
running -> error

paused -> stopping -> stopped
paused -> error

running | pausing | paused | stopping -> emergency_stopping

completed | stopped | error -> idle
```

- `completed`、`stopped`、`error`は1回のシナリオ実行における終端状態とする
- 別のシナリオの選択または再実行準備によって、終端状態から`idle`へ戻す
- `emergency_stopping`の後はバックエンドを終了するため、実行状態の完了通知を保証せず、接続状態が`inactive`となって終了する
- 指令が`failed`になった場合はシナリオ全体を`error`へ移し、後続の待機指令を`execution_failed`でキャンセルする
- 許可されていない状態で受けた操作要求は、`409 Conflict`および`INVALID_STATE`で拒否する

### 8.3 一時停止

- 一時停止要求を受けると、実行状態を`running`から`pausing`へ移す
- 画面ポーリング中の場合は、次のポーリングを行わず結果を待たずに休止し、実行状態を`paused`へ移す
- ポーリングを休止している間も対象の個別指令は`running`のまま保持し、キャンセル扱いにしない
- 再開時は同じコマンドIDのままポーリングを再開する
- 画面クリックの実行中は割り込まず、その1クリックが完了した後に`paused`へ移す
- 一時停止要求後は新しい指令を開始しない
- 待機中の指令は`queued`のまま保持する
- 一時停止中の時間は指令の`durationMs`およびタイムアウト時間へ含めない

### 8.4 通常停止と緊急停止

通常停止では新しい指令の受付と開始を止め、実行状態を`stopping`へ移す。

- ポーリング中は結果を待たずに中断する
- 画面クリックの実行中は割り込まず、その1クリックの完了後に停止する
- 実行中および待機中の指令は`normal_stop`で`cancelled`とする
- 停止処理の完了後、実行状態を`stopped`へ移す

緊急停止は`running`、`pausing`、`paused`、`stopping`のどの状態からでも開始でき、実行状態を`emergency_stopping`へ移す。

- 新しい指令を受け付けない
- ポーリングと実行中の操作を可能な限り即座に中断する
- 実行中および待機中の指令を`emergency_stop`で`cancelled`とする
- フロントエンド切断が原因の場合は`frontend_disconnected`を使用する
- 入力状態の解放とログ記録を行った後、バックエンドを終了する
- SSE切断後はイベントを送れないため、キャンセルイベントの送信完了を保証しない

### 8.5 個別指令状態

```ts
type CommandState = "queued" | "running" | "completed" | "failed" | "cancelled";
```

| 状態 | 意味 |
| --- | --- |
| `queued` | 受付済みで実行待ち |
| `running` | 実行中。ポーリングの一時休止中を含む |
| `completed` | 正常終了 |
| `failed` | エラー終了 |
| `cancelled` | 停止処理または先行指令の失敗によって取り消された |

許可する遷移は次のとおりとする。

```text
queued  -> running
queued  -> cancelled
running -> completed
running -> failed
running -> cancelled
```

- `completed`、`failed`、`cancelled`は終端状態とし、別状態へ遷移しない
- `command.accepted`は受付完了を示すイベント名であり、個別指令状態ではない
- REST受付応答および`command.accepted.data.status`は`queued`とする
- 一時停止では個別指令状態を変更しない

## 9. 安全性

- 元の文字列命令をバックエンドへ送らない
- フロントエンドは文字列命令を型付きコマンドへ変換してから操作APIへ送る
- バックエンドは型付きコマンドを再検証する
- フロントエンドとバックエンドのどちらでも`eval`、`exec`、入力値による動的関数探索を使用しない
- バックエンドはソースコード上に定義した固定の対応表で命令を処理する
