# 配布・起動・復旧手順（Windows）

## 配布と初回セットアップ

リポジトリのソース、`package-lock.json`、`frontend/package-lock.json`、`backend/constraints.txt`、`scenarios`を配布する。Node.js 22、Python 3.12、Chromeを導入し、READMEのセットアップを実行する。依存関係を固定したまま再現するため、npmは`ci`を使う。`.venv`、`node_modules`、`frontend/dist`は配布先で生成する。専用Chromeのプロファイルとログは`.autofgo`に生成される。

## 起動・停止・更新・ログ

- `start-autofgo.cmd`をダブルクリックする。ビルド済み画面がなければ起動は失敗するので、READMEのビルドを実行する。
- 停止は専用Chromeのウィンドウを閉じる。実行中なら先に画面の停止・緊急停止を使う。Pythonと配信サーバーも終了する。
- 更新はChromeを閉じてプロセスの終了を確認し、変更を取得してからREADMEの更新コマンドを実行する。`.env`、`scenarios`、`.autofgo`は更新前にバックアップする。
- ログは`.autofgo/logs/autofgo.log`を確認する。最大2 MB、既定で5世代を保存する。起動前の失敗は復元されたコマンド画面に表示される。

## 攻撃ボタン画像の再採取

ゲーム更新後に攻撃ボタンの画像照合が失敗する場合、LDPlayerを戦闘画面にして攻撃ボタンを表示し、他のウィンドウを重ねずに`collect-attack-sample.cmd`を実行する。案内に従ってキーを押すと、現在のLDPlayerウィンドウ内から20×20ピクセルを採取する。ウィンドウが見つからない場合や想定サイズと異なる場合は採取しない。

採取に成功すると、既存の`backend/src/autofgo/assets/legacy/attack.png`は同じフォルダー内で`attack.YYYYMMDD-HHMMSS.<識別子>.png`へ改名され、新しい`attack.png`が保存される。実行後は新画像の内容を確認し、戦闘画面の検出を確認する。採取位置はアプリ内の固定座標に従うため、ボタン位置やLDPlayerの画面サイズが変わった場合はバッチだけでは対応できない。

## 異常終了後の復旧

1. 自動操作が止まっていることを確認し、残った専用Chromeを閉じる。タスクマネージャーでautoFgoの`python.exe`が残っている場合は、作業ディレクトリやコマンドラインを確認して、このアプリのプロセスだけ終了する。無関係なChromeやPythonを一括終了しない。
2. `.autofgo/logs/autofgo.log`の末尾と起動用ウィンドウのエラーを確認する。`start-autofgo.cmd`から再起動する。実行途中の命令は自動再開しない。
3. 専用プロファイルのロックで起動できない場合は、該当Pythonプロセスが完全に終了したことを確認する。`.autofgo/chrome-profile/.autofgo.lock`に記載されたPIDが稼働中なら、まずそのプロセスを確認する。稼働していないことを確認できた場合だけロックファイルを削除して再起動する。通常は古いロックを自動回収する。
4. プロファイルが破損した場合は、全関連プロセスの終了後に`.autofgo/chrome-profile`を別名へ移して起動する。新しいプロファイルが作成される。必要なChrome内の設定は元のフォルダーに残るので、原因調査後に移す。`.autofgo/logs`や`scenarios`は移さない。
5. ポート8000が使用中なら、PowerShellで`Get-NetTCPConnection -LocalPort 8000 -State Listen | Select-Object OwningProcess`を実行し、`Get-CimInstance Win32_Process -Filter "ProcessId = <PID>"`で所有者を確認する。このアプリの残留プロセスなら終了する。他のアプリなら、起動前のPowerShellで`$env:AUTOFGO_PORT = '8001'`を設定し、`./start-autofgo.cmd`を実行する。設定したポートは専用ChromeのURLにも反映される。

ロックファイルやプロファイルを操作する前に、対応するプロセスが停止していることを確認する。
