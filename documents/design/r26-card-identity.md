# R26 通常カードのキャラクター名識別

## 使用方法

`autofgo.card_identity.CardIdentityRecognizer` はローカル参照データから5枚の名前を判定する。参照画像の読み込み・倍率別画像の準備は初期化時だけ行い、同じ識別器を画面ごとに再利用する。

```python
from pathlib import Path
from PIL import Image
from autofgo.card_identity import CardIdentityRecognizer

recognizer = CardIdentityRecognizer.from_manifest(
    Path("card-data/references/manifest.json")
)
with Image.open("card-data/evaluation/images/battle0/img1.png") as image:
    results = recognizer.recognize(image)
for result in results:
    print(result.position, result.status, result.character_name,
          result.reason, result.score, result.margin)
```

色判定はR25の `detect_card_colors` が担当する。識別器はカードをクリックせず、R28で攻撃実行経路へ接続する。

## 判定

各参照の最小RGB平均絶対差（MAE、0～255、低いほど近い）を小数4桁で保存する。同じキャラの複数衣装・複数参照を1つの名前候補として扱い、最良スコアと最良の**別キャラ**とのスコア差を算出する。同名の別衣装同士は曖昧判定の競合候補にしない。参照候補の `appearance_id` は登録データの情報であり、衣装そのものの確定結果ではない。

`IdentityPolicy` の既定値は `max_mae=40.0`、`min_margin=10.0`。境界はMAE<=40かつ候補差>=10を採用する。候補差も小数4桁にそろえ、浮動小数点誤差で境界が反転しないようにした。

| status | reason | 条件 |
| --- | --- | --- |
| unknown | no_references | 承認済み参照なし |
| unknown | low_similarity | 最良候補でもMAEが上限を超える |
| ambiguous | no_competing_character | MAEは範囲内だが別キャラ候補がない |
| ambiguous | close_candidates | MAEは範囲内だが別キャラ候補との差が不足 |
| recognized | matched | MAEと別キャラとの差が両方の基準を満たす |

`unknown` と `ambiguous` の `character_name` は必ず `None`。最上位候補を確定名へ流用しない。確信度の根拠としてスコア・候補差・判定理由・全参照候補を返す。これらは正解確率ではなく、数値を「90%の確信」などと表示しない。候補差10は暫定の運用基準で、曖昧な実画像群で最適化した値ではない。境界と同点・僅差は合成テストで確認した。

## 参照の読み込み

- schemaVersion整数1、必須文字列、整数寸法、元画像内のcrop、ID重複、reviewedの真偽値を検証する。
- 絶対パス・URL・親ディレクトリ参照・解決後のディレクトリ外パスを拒否する。
- 承認済み画像だけを開き、PNG実体・寸法を検証する。不足・破損は読込エラーとし、候補を黙って減らさない。
- EXIF回転後にRGBへ変換し、透過は白背景へ合成する。resizeメタデータがある場合は元crop寸法に対応する倍率を用いる。
- 検証済みの参照元レイアウトは1920×1080、LDPlayer枠付き1962×1114。その他の参照元サイズは拒否する。

## 探索と高速化

ゲーム領域を480×270へ縮小し、従来の実験と同じ倍率1.3～1.9、元画面4px刻みで総当たりする。5枠のx座標はR25と共有し、各枠の探索幅300px、y=560～850を使う。結果の `game_rect` は正規化した1920×1080ゲーム領域の座標であり、元スクリーンショットの座標ではない。

戦闘画像は1920×1080、LDPlayer枠付き1962×1114を自動判別する。他のサイズはゲーム領域を `viewport` で明示する。正規化は可能だが、別解像度の実画像精度は未検証。

NumPy 2.5.3を依存へ追加した。[sliding_window_view](https://numpy.org/doc/stable/reference/generated/numpy.lib.stride_tricks.sliding_window_view.html) で探索位置をまとめ、差分計算を配列処理する。探索点の間引きは行わない。uint8の引き算による桁あふれを避けるためint16を使い、合計はint64で計算する。8行ずつ処理して一時配列のメモリ量を抑える。参照のリサイズ結果は初期化時に準備する。

## 検証と制約

- [既存17画像の検証](../verification/2026-09-27-R26-existing-dataset.md)で使った全255候補について、Pillow版の保存スコア・倍率・位置と一致することを確認した。
- 登録済み65枚は正しい名前、未登録20枚はunknown。参照は各キャラ1衣装1画像の3枚を維持。
- 画像と正解ラベルを認識処理で混ぜず、実行時は評価manifest・Driveを読まない。
- 名前が同じ複数前衛の区別は名前識別だけではできない。R27の選択側で扱う。
- 17画像は撮影条件が限定され、衣装登録状況はアシスタントの目視評価。未知キャラ全般や他の画面状態への保証はない。
- R28の実行経路、R29のログ・画面表示、R30の実画面検証は後続作業。
