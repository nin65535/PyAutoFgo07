# 自動テスト方針

## 対象と責務

フロントエンドはVitestとTesting Libraryを使用し、JSONスキーマ、文字列コマンドパーサー、SPAの状態遷移、SSE切断、イベント重複防止、シナリオ実行エンジンを検証する。

バックエンドはpytestとFastAPI TestClientを使用し、シナリオIDのパス検証、APIモデル、固定ディスパッチ、直列キュー、停止とキャンセル、SSE、セッショントークンとOrigin検証を検証する。不正入力と緊急停止は独立したテストケースとして扱う。

## OS資産の分離

- `pyautogui`を利用する画面操作は、`FakeBackend`を`ScreenOperator`へ注入する。通常テストではスクリーンショット、クリック、キー入力を実行しない。
- Chrome起動は、プロセス生成関数、実行ファイル探索、プロファイルロックを代替実装またはMockへ差し替える。通常テストではChromeを起動しない。
- ファイルの作成、更新、削除が必要なテストはpytestの一時ディレクトリを使用する。`backend/tests/fixtures`は読み取り専用の固定入力として扱う。
- OS資産を使用するテストは`integration`マーカーを付け、通常のテスト実行から除外する。

## 実行コマンド

```powershell
npm test
npm run test:frontend
npm run test:backend
npm run lint
npm run format:check
npm --prefix frontend run build
```

ルートのnpmスクリプトから実行するPythonコマンドは、プロジェクト直下の`.venv`を明示的に使用する。

OS資産を使用する結合テストは、安全な通常ターミナルから明示して実行する。

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -m integration -o "addopts=-q -p no:cacheprovider"
```
