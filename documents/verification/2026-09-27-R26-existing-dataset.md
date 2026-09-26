# R26 既存17画像の検証

- 実施日: 2026-09-27
- 状態: R26検証中。実行時の識別器は未完成。
- 続報: [本体判定・高速化の検証](2026-09-27-R26-runtime-and-speed.md)で本体の識別器を実装・検証済み。以下は追加画像検証時点の記録。
- 参照: 既存の3キャラ各1衣装1画像を維持。参照画像の追加なし。

## 評価データ

Driveの戦闘0・8画像と戦闘1・9画像をローカルへ取得し、全17画像85カードを照合した。PNGの読み取り、画像寸法1962×1114、正解位置0～4、17件のID一意性を確認した。

名前と色は[Drive README](https://drive.google.com/file/d/1I0VO5TEkQHCvD5cyFwM93JO6fhO3oSqF/view)および[人力確認表](https://docs.google.com/spreadsheets/d/1yTHoIWoF2ERU12JjJfJXax1L-G1jYyUZ9gFvF92tRT4/edit)から `card-data/evaluation/manifest.json` へ転記した。戦闘1の全9行に「正しい」の確認がある。人力確認済みなのは名前と色であり、衣装の登録状況ではない。

衣装の登録状況は、照合スコアとは別に参照画像と戦闘画像をアシスタントが目視比較し、`r26-appearance-review.json` に記録した。ユーザーによる衣装ラベルの確認とは扱わない。衣装の正式なIDは付与していない。

- 戦闘0: img1～5は全て登録済み。img6～8はアーラシュのみ登録済み。別衣装への変更はREADMEにも記載されている。
- 戦闘1: アーラシュとダイダロスは登録済み。バーヴァン・シーは181853～182252では未登録、182416以降は登録済みの絵柄。
- 合計: 登録済み65枚、未登録20枚。
- img1～5は同じ配布の連続撮影。集計は13 captureGroupに分け、85枚を独立試行と呼ばない。戦闘1も同じ撮影環境の連続した資料であり、統計的な独立性を保証しない。

## 初回条件を維持した追加評価

`r26_match.py` の既定値（探索上端y=600、倍率1.3～1.9、RGB MAE）を維持した。採否は前回の2画像で観測した仮境界MAE<=40を固定して集計した。照合スクリプトは正解ラベルを読まず、`r26_evaluate.py` が出力後に正解と比較する。

| 対象 | 登録済みの正しい採用 | 登録済みの判定保留 | 未登録衣装の拒否 | 採用した名前の誤り |
| --- | ---: | ---: | ---: | ---: |
| 追加15画像・75枚 | 49 | 8 | 18 | 0 |
| 初回2画像を含む17画像・85枚 | 57 | 8 | 20 | 0 |

判定保留8枚は全てダイダロスで、戦闘0のimg3・img5で各2枚、戦闘1の181853で2枚、181955・182125で各1枚。正しい名前は最上位でもMAEが40を超えていた。

カードが上に揺れたときに探索上端へ最良矩形が接しており、顔周辺の一致位置を探索範囲が取りこぼしている可能性があった。img3で探索上端だけを560へ広げると、ダイダロスの2枚はMAE=42.1475→27.2678、41.1180→23.6025になった。参照データを増やさずに改善できた。

## 探索上端を560へ広げた再評価

倍率・参照画像・MAE境界40を維持し、探索上端のみ600→560へ変更して全17画像を再照合した。

| 対象 | 登録済みの正しい採用 | 登録済みの判定保留 | 未登録衣装の拒否 | 採用した名前の誤り |
| --- | ---: | ---: | ---: | ---: |
| 追加15画像・75枚 | 57 | 0 | 18 | 0 |
| 全17画像・85枚 | 65 | 0 | 20 | 0 |

登録済み65枚のMAEは7.7538～32.7953、未登録20枚の最良MAEは56.2990～63.5425だった。登録済みの別キャラとの差は最小31.2370。今回の範囲では境界40の両側に分離した。以前の判定保留8枚は全て改善した。

登録済み65枚の色はBuster 25枚、Arts 31枚、Quick 9枚。緑背景の各1参照のままで、3色を含む名前照合を確認できた。色ラベルは集計用であり、今回R25の色判定処理を再検証したという意味ではない。

拡張後の処理時間は1画像7.670～8.807秒。初期条件の実行では5.425～19.852秒とばらつきがあり、一部の実行時間が重なるため、この値を厳密な速度比較とは扱わない。いずれも実運用前に高速化が必要。

既存の参照3枚で、この資料内の登録済み絵柄と未登録絵柄を分ける見込みが得られた。今回の問題に対して参照画像を増やす必要はなかった。

## 再現手順

原画像はGit管理外。manifestのsourceUrlから対応するPNGを取得し、imagePathへ配置する。

```powershell
$imagesR26 = Get-ChildItem card-data/evaluation/images -Recurse -Filter *.png | Sort-Object FullName | ForEach-Object { Resolve-Path -Relative $_.FullName }
.\.venv\Scripts\python.exe backend/experiments/r26_match.py @imagesR26 --output documents/verification/r26-all-scores.json
.\.venv\Scripts\python.exe backend/experiments/r26_evaluate.py --scores documents/verification/r26-all-scores.json --output documents/verification/r26-all-evaluation.json
.\.venv\Scripts\python.exe backend/experiments/r26_match.py @imagesR26 --search-top 560 --output documents/verification/r26-expanded-scores.json
.\.venv\Scripts\python.exe backend/experiments/r26_evaluate.py --scores documents/verification/r26-expanded-scores.json --output documents/verification/r26-expanded-evaluation.json
```

評価処理はmanifestの全17画像を要求する。画像の不足やハッシュの変化はエラーにし、黙って評価対象から除外しない。候補スコア、矩形、倍率、SHA-256、時間は各scores JSON、カード単位の採否とcaptureGroup別集計は各evaluation JSONを参照。

## 制約と次の作業

- 探索範囲の変更はこの17画像を見て決定したため、変更後の評価は調整済みデータでの再評価である。独立した未知画像への精度保証にはしない。
- MAEは正解確率ではない。絶対値だけでなく別キャラ候補との差を用いる曖昧判定、閾値の設定方法は本体の識別器で検討が必要。
- 未登録20枚はこの資料内の別衣装であり、未知キャラ全般、未知背景、別解像度を代表しない。
- 検証コードはPillowによる総当たりで、実運用向けの速度改善とmanifestの厳密な入力検証は未対応。
- R26のロードマップは未完了を維持。R28～R30への接続・実画面実行は行っていない。
