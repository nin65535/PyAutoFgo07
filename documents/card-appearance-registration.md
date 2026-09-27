# キャラクターの衣装データ追加手順（現行CLI）

ステータス画面右側の小さなコマンドカードから、既存キャラクターの衣装参照画像を追加する現行CLIの手順。プレイヤーとは別に起動する専用サンプラーアプリの仕様は [カード参照サンプラーアプリ仕様](design/card-sampler-app.md) にまとめる。専用アプリは未実装であり、以下のCLIでは切り出し座標を手動で指定する。IDと画像名は自動採番する。

以下のコマンドはプロジェクト直下の PowerShell で実行する。Python は必ず `.venv` のものを使う。元画像の保管場所は Google Drive の[カード認識サンプル](https://drive.google.com/drive/folders/1TC2WXNYMlpOSJbk2vNo8WlUga1iM-Z9o)を基準とし、取得した元画像は Git に追加しない。

## 1. 衣装と元画像を確認する

1. ステータス画面のスクリーンショットを用意し、キャラクターの正式表記と衣装・再臨段階を人が確認する。`scenarios/*.json` の `members`（全角 `＋` 以降と末尾の ` guest` は注釈として除く）に名前があることを調べる。参照manifestにまだない名前なら、そのキャラクターの最初の衣装として登録する。`scenarios` にないキャラクターはこの手順で追加しない。
2. 同じ衣装ならmanifest内の数値 `appearanceId` を確認して使う。新しい衣装なら指定を省き、自動採番する。画像の色やファイル名だけから衣装を推定しない。
3. 元画像を識別する `sourceId` を決める。参照 `id` とサンプル番号は自動採番する。
4. 元画像上で右側の小さなコマンドカードの絵柄を囲む矩形を測る。座標は `left,top,width,height` のピクセル値で、右端と下端を含まない。元画像の向きは EXIF 回転を適用した後のものを使う。

衣装を確認できない場合は承認済み参照として登録しない。`reviewed: false` の参照は識別候補に入らない。

## 2. 切り出しをプレビューする

`<元画像>`、`<座標>`、`<プレビュー先>`を実際の値に置き換える。

```powershell
.\.venv\Scripts\python.exe -m autofgo.card_sampler preview --input "<元画像>" --crop <left,top,width,height> --output "<プレビュー先>.png"
```

生成した PNG を開き、顔や衣装の特徴が欠けず、別の UI が入り込んでいないことを確認する。ずれていれば座標を変えて再実行する。既存の参照画像はおおむね 105～110 × 100 ピクセルだが、数値を流用せず元画像に合わせて測る。

## 3. 参照を登録する

名前と衣装を人が確認できたときだけ `--confirmed` を付ける。Drive 上の元画像なら `--source-url` にそのファイルの URL を指定する。ローカル画像しかない場合、この引数は省略できる。

```powershell
.\.venv\Scripts\python.exe -m autofgo.card_sampler register --input "<元画像>" --crop <left,top,width,height> --character-name "<正式なキャラクター名>" --source-id "<元画像ID>" --source-url "<元画像URL>" --confirmed
```

既存衣装へ追加する場合だけ `--appearance-id <数値>` を付ける。成功すると `card-data/references/images/<キャラクター名>-<衣装ID>-<サンプル番号>.png` とmanifestの1件が作られる。既存画像への上書きは拒否する。まずは1衣装1画像で確認し、必要が判明したときだけ増やす。

## 4. 登録内容と判定を確認する

1. manifest の新規エントリで `characterId`、`appearanceId`、`sampleNumber`、`reviewed: true`、`source` の出典・元画像サイズ・切り出し座標、`imageSize` と `imagePath` を確認する。PNG を開いてプレビューした絵柄と一致することも確認する。
2. `card-data/evaluation/manifest.json` の正解データとは分けて扱う。新しい戦闘画像を評価に加える場合は、左から5枚の名前と色を人が確認して記録する。`appearanceId` は衣装を個別に確認できたカードにだけ付ける。
3. 対象衣装の戦闘画像で正しい名前に判定されることを確認し、既存画像でも別キャラクターへの誤判定が増えていないことを確認する。スコアだけで正解と判断しない。実機で確かめる場合は、安全に停止できる状態で実行し、カードの選択結果を確認する。
4. 変更した manifest と切り出し PNG を Git の差分で確認する。元のスクリーンショットやプレビュー画像は、必要な小さなテストデータとして採用する場合を除き Git に追加しない。

既存の登録や評価データの仕様は [R23 カード画像データ](design/r23-card-image-data.md)、サンプラーの基本操作は [R24 サンプラー](design/r24-card-sampler.md)、判定条件は [R26 カード識別](design/r26-card-identity.md)を参照する。
