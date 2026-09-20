# 指令キューと実行状態管理

## 概要

バックエンドは受け付けた型付き指令を単一ワーカースレッドで処理し、同時に複数の画面操作を実行しない。指令IDはプロセス内で一意とし、同一内容の再送には既存の指令状態を返す。異なる内容で同じIDを再利用した場合は拒否する。

## 個別指令

各指令は、指令ID、型付き指令、受付・開始・終了時刻、状態、結果、エラー種別、キャンセル理由を保持する。状態遷移は共通仕様どおり、次に限定する。

```text
queued -> running -> completed
                  -> failed
queued  -> cancelled
running -> cancelled
```

ハンドラーの想定外例外はワーカースレッドの境界で捕捉し、外部へ例外メッセージを公開せず例外型だけを内部状態へ記録する。失敗後の待機指令は`execution_failed`でキャンセルする。

## 実行制御

- 最初の指令受付時に`idle`から`running`へ移る。
- 一時停止要求は、実行中指令がある場合に`pausing`へ移り、安全なチェックポイント到達後に`paused`へ移る。待機指令は開始しない。
- 再開要求は`paused`または`pausing`から`running`へ戻す。
- 通常停止は受付を閉じ、キャンセル通知を実行中指令へ送り、待機指令を`normal_stop`で破棄する。実行中指令の終了後に`stopped`へ移る。
- 緊急停止は通常キューより先にロック内で受付停止、キャンセル通知、待機指令破棄を行い、`emergency_stopping`へ移る。プロセス終了と入力解放はR10で接続する。
- ハンドラーは`ExecutionControl.checkpoint()`を安全な処理境界で呼び、一時停止とキャンセルを協調的に反映する。

## REST API

指令受付に加えて、次のエンドポイントを提供する。

```http
GET  /api/commands/status
POST /api/commands/pause
POST /api/commands/resume
POST /api/commands/stop
POST /api/commands/emergency-stop
```

状態取得は現在の実行状態、実行中指令ID、待機件数、受付可否を返す。不正な状態遷移は`409 INVALID_STATE`、停止後の指令受付は`503 SERVICE_UNAVAILABLE`とする。状態変更のSSE通知はR08で追加する。
