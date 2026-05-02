# 2026-04-26 APP_MODE追加修正

## 修正内容

### 1. 本番モードでQuick Startを非表示
本番環境では、営業デモ用の「よくある問い合わせ」「すぐ試せる代表質問」ボタンを表示しないようにしました。

対象ファイル:
- helpdesk_app/modules/quick_start_panel.py

動作:
- APP_MODE = "demo" の場合: Quick Startを表示
- APP_MODE = "production" の場合: Quick Startを非表示

### 2. サイドバーのログ系表示を削除
左側サイドバーに出ていたログ系メニューを削除しました。

削除したサイドバー表示:
- 問い合わせログ状況（該当なし）
- 削減時間シミュレーター
- ログ（該当なし）ダウンロード
- 最新ログCSVダウンロード
- ログZIPダウンロード
- ログ一覧を見る

対象ファイル:
- helpdesk_app/modules/main_view_runtime.py

### 3. ログ系は管理者ログイン後の中央エリアに集約
ログ閲覧・一括ダウンロードは、既存の管理者エリア内にある
「📝 ログ閲覧 / 一括ダウンロード」で表示されます。

対象ファイル:
- helpdesk_app/modules/admin_complete_sections.py
- helpdesk_app/modules/admin_log_download_panel.py

## 設定方法

デモ用:
APP_MODE = "demo"

本番用:
APP_MODE = "production"

未設定時は既存挙動維持のため demo として動作します。
