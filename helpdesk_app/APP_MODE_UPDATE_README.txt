APP_MODE によるデモ用 / 本番用 画面切替を追加しました。

■ 設定方法
.streamlit/secrets.toml または環境変数で設定します。

デモ用（既存と同じ営業向け画面）:
APP_MODE = "demo"

本番用（顧客利用向け画面）:
APP_MODE = "production"

未設定時は既存挙動を壊さないため demo として動作します。

■ デモ用で表示されるもの
・導入相談ボタン
・固定の相談ボタン
・導入相談CTAパネル
・営業デモサマリーKPI
・営業向けの説明文
・導入相談リンク

■ 本番用で非表示 / 簡略化されるもの
・導入相談ボタン
・固定の相談ボタン
・導入相談CTAパネル
・営業デモサマリーKPI
・営業向け説明文
・サイドバーの営業用説明

■ 追加・修正ファイル
・modules/app_mode.py
・runtime_main.py
・modules/app_bootstrap.py
・modules/app_surface_runner.py
・modules/main_view_runtime.py
・modules/chat_history_panel.py
・modules/quick_start_panel.py

