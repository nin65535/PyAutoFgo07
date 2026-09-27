# R31 参照データの数値IDと採番

参照manifestだけを `schemaVersion: 2` に更新する。評価manifestは `schemaVersion: 1` のまま保持し、人が確認した正解ラベルは変更しない。旧形式の仕様と採取時の経緯は [R23](r23-card-image-data.md) に残す。

```json
{
  "schemaVersion": 2,
  "nextCharacterId": 5,
  "nextReferenceId": 10,
  "characters": [
    {"id": 1, "name": "アーラシュ", "nextAppearanceId": 2, "appearances": [1], "nextSampleNumbers": {"1": 2}}
  ],
  "references": [
    {
      "id": 1,
      "characterId": 1,
      "appearanceId": 1,
      "sampleNumber": 1,
      "imagePath": "images/アーラシュ-1-01.png",
      "imageSize": [105, 100],
      "source": {"kind": "statusScreenshot", "sourceId": "arash-status-162859", "sourceSize": [1962, 1114], "crop": [832, 445, 105, 100]},
      "reviewed": true
    }
  ]
}
```

`characterId` は全体で一意、`appearanceId` はキャラクター内で一意、`id` は参照全体で一意とする。採番済みの番号は削除後も再利用しない。キャラクター、衣装、衣装ごとのサンプル、参照の次番号をmanifestのカウンターで保持する。新規登録では既存衣装IDを指定するか、新衣装を自動採番する。CLIから参照IDやサンプル番号を指定できない。

既存9件は従来のmanifest配列順で数値参照IDを1～9へ割り当てた。キャラクターIDはアーラシュ1、ダイダロス2、バーヴァン・シー3、オベロン4。衣装IDは各キャラクターの旧参照の初出順で1から割り当てた。既存PNGのバイト列と切り出し座標は変更せず、ファイル名だけを `<キャラクター名>-<衣装ID>-<サンプル番号>.png` に変更した。

検証と採番と保存は `autofgo.card_references` をプレイヤーの識別器と現行CLIで共有する。未知版、文字列ID、重複、画像名とIDの不一致、危険なパスを拒否する。承認済み参照のみ識別器に渡す。PNG作成後にmanifestを原子的に置き換え、失敗時には新PNGを削除する。専用サンプラーAPIはR33でこの保存処理を呼ぶ。
