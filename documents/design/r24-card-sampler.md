# R24 カード参照画像サンプラーの使い方

ステータス画面右側の小さなコマンドカードの絵柄領域を元画像のピクセル座標で指定する。元画像はローカルに置き、Gitへ登録しない。画像の向きはEXIF回転を適用した後のものとする。

```powershell
.\.venv\Scripts\python.exe -m autofgo.card_sampler preview --input status.png --crop 1000,200,48,48 --output preview.png
```

`preview.png` を開いて絵柄、キャラクター名、衣装を確認する。必要なら `--crop` を変えて再実行する。座標は `left,top,width,height` で、右端と下端を含まない。

```powershell
.\.venv\Scripts\python.exe -m autofgo.card_sampler register --input status.png --crop 1000,200,48,48 --id arash-default-01 --character-name アーラシュ --appearance-id default --source-id arash-status-01 --confirmed
```

登録すると `card-data/references/images/<id>.png` と manifest の1件が作られる。出典URLがある場合は `--source-url` で指定する。`--confirmed` はプレビューと名前・衣装を人が確認した場合にだけ付ける。追加登録は新しい `id` を指定する。再作成は対象エントリとPNGを取り除いてから同じ `id` で登録する。既存の `id` や画像への上書きは拒否する。

画像の切り出しとRGB変換はサンプラーに閉じ、識別器側では保存したPNGとmanifestを読む。戦闘画面画像や正解ラベルは登録入力にしない。
