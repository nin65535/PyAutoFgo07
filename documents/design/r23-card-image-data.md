# R23 カード画像の参照データと正解データの形式

## 用途と配置

サンプラーと識別器は、ローカルの `card-data/references/manifest.json`（UTF-8 JSON）を共有する。参照画像はステータス画面右側の小さなコマンドカードから切り出した PNG とし、`card-data/references/images/` に置く。識別器は承認済みエントリだけを読み、キャラクター名の判定に使う。色は戦闘画面から別途判定し、参照画像の色を正解として使わない。

検証用の戦闘画像と人力確認ラベルは `card-data/evaluation/manifest.json` に分離する。実行時の識別器とサンプラーはこのファイルを読まない。検証プログラムは画像と正解ラベルを読み、推定結果と比較する。実行時に Drive へ接続しない。

`card-data/` の JSON、承認済みの切り出し PNG、および再現に必要な小さなテスト画像は Git で管理する。元のステータス画面・戦闘画面のスクリーンショットは大きさと出典の管理を考慮し Git に含めず、Drive の[カード認識サンプル](https://drive.google.com/drive/folders/1TC2WXNYMlpOSJbk2vNo8WlUga1iM-Z9o)を原本とする。検証用画像は利用者が `card-data/evaluation/images/` にローカル配置する。欠けた画像がある検証は黙って除外せず、不足を報告する。両 manifest と画像の実体は R24 以降で作成する。

## 共通規則

- 両 manifest の `schemaVersion` は整数 `1`。読み手は未知の版を拒否する。保存時は UTF-8、相対パス区切りは `/`。
- `imagePath` は manifest 所在ディレクトリからの相対パス。絶対パス、`..`、URL、ディレクトリ外へ解決されるパスを許さない。画像の実体は PNG とする。Drive URL は出典情報にだけ記録する。
- `sourceSize` と矩形は**元画像のピクセル座標**。左上が `(0, 0)`、矩形は `[left, top, width, height]`、右端・下端は含まない。整数で `width`・`height` は正、矩形全体が画像内に収まることを検証する。EXIF 回転を適用した後の向きで記録する。
- `id` は manifest 内で一意の永続識別子。表示名を変更しても再利用しない。`characterName` はゲーム画面・シナリオの `members` と照合する正式表記とする。衣装を区別する `appearanceId` は同一キャラクター内で安定させ、画像ファイル名やカード色に依存させない。
- 各 JSON は下記の必須フィールドを持つ。将来の追加フィールドは版を上げるか、旧版の読み手が無視できる任意フィールドとして明示する。R24・R26で読み書きと検証を実装する。

## 参照データ `references/manifest.json`

```json
{
  "schemaVersion": 1,
  "references": [
    {
      "id": "arash-default-01",
      "characterName": "アーラシュ",
      "appearanceId": "default",
      "imagePath": "images/arash-default-01.png",
      "imageSize": [48, 48],
      "source": {
        "kind": "statusScreenshot",
        "sourceId": "arash-status-01",
        "sourceUrl": "https://drive.google.com/drive/folders/17LJC4rFLY5qm-W2tr9LdU3Rtp-TAIA64",
        "sourceSize": [1280, 720],
        "crop": [1000, 200, 48, 48]
      },
      "reviewed": true
    }
  ]
}
```

この例の `imageSize`・`sourceSize`・`crop` は**形式説明用の仮値**で、Drive 原画像の実測値ではない。実データ作成時には測定した値を入れる。`imageSize` は保存した切り出し PNG の寸法で、`crop` と一致するか、縮小・拡大した場合は次の `transform` を記録する。`sourceId` は元画像を識別する安定名、`sourceUrl` は任意の出典 URL。ローカル画像なら `sourceUrl` は省略できる。`reviewed` は切り出しとキャラクター名・衣装を人が確認した場合だけ `true` とする。

加工した画像には任意の `transform` を付け、`{"resize": [48, 48], "resample": "LANCZOS"}` のように最終寸法と再サンプリング法を記録する。加工なしなら `transform` は省略する。色空間は RGB、透過があれば白背景に合成して保存する。照合の倍率・探索範囲・閾値は識別器側の設定であり、画像そのものの来歴には含めない。

同じ衣装から複数の切り出しを採る場合は、`characterName` と `appearanceId` を共有し、異なる `id` と `imagePath` を与える。別衣装は必ず異なる `appearanceId` とする。登録時に同一人物の衣装が判別できない場合は `reviewed: false` として識別候補へ入れない。

## 正解データ `evaluation/manifest.json`

```json
{
  "schemaVersion": 1,
  "cases": [
    {
      "id": "battle0-img1",
      "imagePath": "images/battle0/img1.png",
      "sourceUrl": "https://drive.google.com/drive/folders/1w6N8nzpdvEgt3NEPg8WLQbLaYWN85e76",
      "sourceSize": [1280, 720],
      "captureGroup": "battle0-same-deal-1",
      "review": "documented",
      "cards": [
        {"position": 0, "color": "B", "characterName": "ダイダロス"},
        {"position": 1, "color": "A", "characterName": "アーラシュ"},
        {"position": 2, "color": "A", "characterName": "バーヴァン・シー"},
        {"position": 3, "color": "A", "characterName": "ダイダロス"},
        {"position": 4, "color": "B", "characterName": "アーラシュ"}
      ]
    }
  ]
}
```

ここでも `sourceSize` は形式説明用の仮値。1ケースは戦闘画面の1画像で、`cards` は画面左から右へ `position` 0～4 を重複なく全て持つ。`color` は `B`（Buster）、`A`（Arts）、`Q`（Quick）のいずれか。正解に衣装を追加する場合は人が個別に確認した `appearanceId` のみ任意で付け、絵柄からの推定を正解に混ぜない。

`review` は `documented`（資料に正解ラベルが記載）か `humanConfirmed`（人が確認済み）。Drive の戦闘0は前者、戦闘1の9画像は後者とする。`captureGroup` は同じ配布の連続撮影を束ね、集計時に独立試行として数えないための識別子。独立した撮影にも固有の値を付ける。画像の効果表示などは任意の `notes` 文字列に記録できる。`sourceUrl` は出典を示し、ファイルを取りに行くための実行時パスではない。

## 既存資料との対応と検証境界

Drive の [README](https://drive.google.com/file/d/1I0VO5TEkQHCvD5cyFwM93JO6fhO3oSqF/view) の戦闘0・8画像の表は `documented`、戦闘1・9画像の[人力確認表](https://docs.google.com/spreadsheets/d/1yTHoIWoF2ERU12JjJfJXax1L-G1jYyUZ9gFvF92tRT4/edit)は `humanConfirmed` として転記する。戦闘0の img1～img5 は同じ `captureGroup` にする。転記時は画像名・5枚の順番・色・名前を原資料と照合する。元画像の寸法、切り出し座標、衣装 ID は原資料から推測せず、R24 の採取・確認時に決定する。

参照データの登録・調整に使った画像を検証に含める場合、精度評価では「登録に利用」と明示する。正解ラベルは照合・閾値調整の入力に使わない。正解データの枚数だけを独立した成功試行数として報告せず、`captureGroup` ごとの内訳も示す。
