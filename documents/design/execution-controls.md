# 実行コントロール設計

## 操作と状態

フロントエンドは起動時およびSSE接続確立時に`GET /api/commands/status`で状態を同期し、以後はAPI応答と`execution.state_changed`イベントを反映する。

| 操作 | 許可する状態 | API |
| --- | --- | --- |
| 開始 | `idle`、`stopped`、`completed` | `POST /api/commands/start` |
| 一時停止 | `running` | `POST /api/commands/pause` |
| 再開 | `pausing`、`paused` | `POST /api/commands/resume` |
| 通常停止 | `running`、`pausing`、`paused` | `POST /api/commands/stop` |
| 緊急停止 | バックエンド接続中 | `POST /api/commands/emergency-stop` |

開始には、バックエンドへの接続と検証済みシナリオの選択も必要とする。API要求の処理中は重複操作を防ぐため全コントロールを一時的に無効化する。

R20の画面では、独立した開始ボタンや実行対象ラジオボタンは置かない。All/Waveの各実行ボタンが対象選択と開始を兼ねる。命令詳細表示、完了件数、Space一時停止を含む最終UI仕様は`r20-wave-and-compact-ui.md`を参照する。

## 誤操作防止

- 実行中、一時停止処理中、一時停止中、停止処理中、緊急停止処理中はシナリオ選択を無効化する。
- 現在の状態で無効な遷移に対応するボタンは無効化する。
- 緊急停止は画面上部の追従領域に常時配置し、接続断または緊急停止処理中だけ無効化する。
- APIが操作を拒否した場合は状態を推測で変更せず、ユーザー向けエラーをコントロール直下へ表示する。

## R14との境界

R13の開始操作は実行状態を`running`へ移す。検証済みコマンドの送信、SSE完了通知を使った次命令の決定、現在位置とタイムアウトの管理はR14で実装する。
