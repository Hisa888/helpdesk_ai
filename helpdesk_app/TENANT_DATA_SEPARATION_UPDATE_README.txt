# 会社ID別データ分離 修正内容

## 目的
TENANT_USERS に demo / c1 / aaa など複数会社IDを追加した場合、会社ごとに FAQ / DB / RAG / ログ / 設定 を分けて保存するための修正です。

## ローカル保存先
ログインした会社IDごとに、以下のフォルダを自動作成します。

- runtime_data/tenants/demo/
- runtime_data/tenants/c1/
- runtime_data/tenants/aaa/

各会社フォルダの中に以下を保存します。

- faq.csv
- helpdesk.db
- logs/
- doc_rag/
- search_settings.json
- ui_theme_settings.json
- ui_layout_settings.json
- llm_settings.json

## DBについて
FAQ DBは会社IDごとに以下のように作成されます。

- runtime_data/tenants/demo/helpdesk.db
- runtime_data/tenants/c1/helpdesk.db
- runtime_data/tenants/aaa/helpdesk.db

TENANT_USERS に会社を追加しただけでは、その会社にログインするまでDBは作成されません。
初回ログイン時に自動作成されます。

## GitHub永続化を使う場合
以前は GitHub 保存先が faq.csv / logs/ で全社共通になりうる状態でした。
今回から以下のように会社ID別で保存します。

- streamlit_data/tenants/demo/faq.csv
- streamlit_data/tenants/c1/faq.csv
- streamlit_data/tenants/aaa/faq.csv

これにより、複数会社のFAQやログが混ざることを防ぎます。

## secrets.toml 例

TENANT_USERS = [
  "demo:demo:demo:デモユーザー:user",
  "c1:user1:user123:デモユーザー:user",
  "aaa:user1:user123:AAA会社:user",
  "demo:admin:password:管理者:admin"
]

形式:
会社ID:ログインID:パスワード:表示名:権限
