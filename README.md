# autoFgo

ゲーム画面の監視と操作を、JSONで定義した手順に従って実行するローカルアプリケーションです。

## 必要な環境

- Node.js 22（セットアップ・更新時のビルドに使用）
- Python 3.12
- Google Chrome（通常のインストール先、または `.env` の `AUTOFGO_CHROME_EXECUTABLE`）

## セットアップ

```powershell
npm ci
npm --prefix frontend ci
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -c .\backend\constraints.txt -e ".\backend[dev]"
npm --prefix frontend run build
```

必要なら `.env.example` を `.env` にコピーして設定を上書きします。
操作手順JSONは既定でプロジェクト直下の`scenarios`へ配置します。保存場所は
`AUTOFGO_SCENARIO_DIRECTORY`で変更できます。

## 通常の起動・停止

Windowsでは、プロジェクト直下の `start-autofgo.cmd` をダブルクリックすると、
`.venv`のPythonがビルド済み画面とAPIを単一ポートから配信し、専用Chromeを起動します。
通常起動時にNode.jsやViteは動作しません。専用Chromeを閉じると
正常終了して起動用ウィンドウも閉じます。起動失敗や異常終了時はエラーを表示し、
キー入力までウィンドウを開いたままにします。ログは
`.autofgo/logs/autofgo.log` に保存します。初回は上記のセットアップが必要です。
起動用ウィンドウは実行中に最小化され、異常終了した場合だけ元に戻ります。

更新時は専用Chromeを閉じて終了を待ち、変更を取得した後に
`npm ci`、`npm --prefix frontend ci`、`.\.venv\Scripts\python.exe -m pip install -c .\backend\constraints.txt -e ".\backend[dev]"`、
`npm --prefix frontend run build` を再実行してください。`scenarios` と `.env` は更新前に別途バックアップしてください。

異常終了、ポート競合、プロファイル破損からの復旧方法は
[運用・復旧手順](documents/operations.md)を参照してください。

## 開発コマンド

```powershell
npm run dev          # フロントエンドとバックエンドを同時起動
npm run lint         # ESLint と Ruff
npm run format       # Prettier と Ruff formatter
npm run format:check # Prettier と Ruff formatter の差分確認
npm test             # Vitest と pytest
npm run test:frontend
npm run test:backend
npm --prefix frontend run build
```

ルートのnpmスクリプトを含め、バックエンドのPythonコマンドは常にプロジェクト直下の
`.venv`を使用します。通常のpytestはOS資産を使用しない単体テストだけを実行し、キャッシュを残しません。
実ファイルシステムを使う結合テストは、サンドボックス外の通常ターミナルから明示的に実行します。

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -m integration -o "addopts=-q -p no:cacheprovider"
```

開発時のフロントエンドは `http://127.0.0.1:5173`、API は `http://127.0.0.1:8000` で待ち受けます。Vite は `/api` をバックエンドへプロキシします。

専用Chromeを含めて起動する場合は、先にフロントエンドを起動し、別のターミナルから
Pythonエントリーポイントを実行します。バックエンドの待受開始後、専用プロファイルと
左上200×1000ピクセルのアプリウィンドウでChromeが自動起動します。

```powershell
npm run dev:frontend
.\.venv\Scripts\python.exe -m autofgo
```

Chromeの場所、プロファイル保存先、表示URL、ウィンドウ位置・サイズは `.env` で変更できます。
設定項目は `.env.example` を参照してください。同じ専用プロファイルを使用するautoFgoが
起動済みの場合、二重起動を拒否します。

ライブラリは2026-09-20時点の安定版へ固定しています。npm依存は各 `package.json` と `package-lock.json`、Python依存は `backend/pyproject.toml` と `backend/constraints.txt` で管理します。TypeScriptは、`typescript-eslint` が対応する最新安定版の6.0.3を使用します。

設計資料は [documents/design/basic-design.md](documents/design/basic-design.md)、作業順は [documents/roadmap.md](documents/roadmap.md) を参照してください。
