# Card identity fixtures

`manifest.json` と3枚のPNGは2026-09-27時点の `card-data/references` の固定コピー。
テストから変更しない。書き込みを検証するテストは作業用コピーを使用する。

`decisions.json` は `documents/verification/r26-expanded-scores.json` の全候補スコアと
`r26-expanded-evaluation.json` の期待名（未登録衣装はnull）を抽出した85枚の固定回帰データ。
名前・色の原典はDriveのREADMEと人力確認表、衣装登録の評価はアシスタントの目視比較。
これは判定ロジックの回帰用であり、画像照合の再計算や独立データでの精度検証ではない。
画像照合の全17画像再計算は `backend/experiments/r26_verify_runtime.py` を使う。
