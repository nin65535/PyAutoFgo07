# autoFgo

ゲーム画面の監視と操作を、JSONで定義した手順に従って実行するローカルアプリケーションです。

## 必要な環境

- Node.js 22
- Python 3.12

## セットアップ

```powershell
npm install
npm --prefix frontend install
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -c .\backend\constraints.txt -e ".\backend[dev]"
```

必要なら `.env.example` を `.env` にコピーして設定を上書きします。

## 開発コマンド

```powershell
npm run dev          # フロントエンドとバックエンドを同時起動
npm run lint         # ESLint と Ruff
npm run format       # Prettier と Ruff formatter
npm test             # Vitest と pytest
npm --prefix frontend run build
```

開発時のフロントエンドは `http://127.0.0.1:5173`、API は `http://127.0.0.1:8000` で待ち受けます。Vite は `/api` をバックエンドへプロキシします。

ライブラリは2026-09-20時点の安定版へ固定しています。npm依存は各 `package.json` と `package-lock.json`、Python依存は `backend/pyproject.toml` と `backend/constraints.txt` で管理します。TypeScriptは、`typescript-eslint` が対応する最新安定版の6.0.3を使用します。

設計資料は [documents/basic-design.md](documents/basic-design.md)、作業順は [documents/roadmap.md](documents/roadmap.md) を参照してください。
