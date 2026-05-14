# ログイン画面の初期案内メッセージ削除

## 修正内容

ログイン画面下部に表示されていた以下の案内メッセージを削除しました。

- 初期状態では demo / demo / demo でログインできます。
- 本番では .streamlit/secrets.toml の TENANT_USERS を必ず変更してください。
- 管理者権限を付ける場合は TENANT_USERS に ... role=admin を指定します。

## 対象ファイル

- helpdesk_app/modules/tenant_auth.py

## 既存機能

会社IDログイン、TENANT_USERS によるユーザー認証、管理者権限判定は削除していません。
表示メッセージのみ削除しています。
