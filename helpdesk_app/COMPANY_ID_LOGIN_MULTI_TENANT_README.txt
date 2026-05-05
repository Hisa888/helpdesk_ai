# 会社IDログイン + company_id分離対応

## 追加内容

1. 起動直後にログイン画面を表示
   - 会社ID
   - ログインID
   - パスワード

2. 会社IDごとにデータを分離
   - FAQ CSV
   - SQLite DB
   - RAGアップロードデータ
   - 問い合わせログ
   - UI設定
   - LLM設定
   - 検索精度設定

3. 分離先フォルダ

runtime_data/tenants/{会社ID}/
  ├ faq.csv
  ├ helpdesk.db
  ├ logs/
  ├ search_settings.json
  ├ ui_theme_settings.json
  ├ ui_layout_settings.json
  └ llm_settings.json

例:
runtime_data/tenants/demo/
runtime_data/tenants/customer-a/
runtime_data/tenants/customer-b/

## 初期ログイン

初期状態では、検証用として以下でログインできます。

会社ID: demo
ログインID: demo
パスワード: demo

※ 本番利用では必ず変更してください。

## .streamlit/secrets.toml 設定例

### 形式1: 文字列

TENANT_USERS = "demo:demo:demo, customer-a:sato:pass123, customer-b:tanaka:pass456"

### 形式2: 配列

TENANT_USERS = [
  "demo:demo:demo",
  "customer-a:sato:pass123",
  "customer-b:tanaka:pass456"
]

### 形式3: テーブル形式

[TENANT_USERS]
"demo/demo" = "demo"
"customer-a/sato" = "pass123"
"customer-b/tanaka" = "pass456"

### 形式4: 会社ごとに複数ユーザー

[TENANT_USERS]
demo = "demo:demo"
customer-a = "sato:pass123,suzuki:pass789"
customer-b = "tanaka:pass456"

## 注意点

- 会社IDは半角英数字、ハイフン、アンダースコア推奨です。
- 日本語や記号を入れた場合は安全なIDに変換されます。
- 既存の管理者ログインは残しています。
- 会社ログインはアプリ全体の入口です。
- 管理者ログインはFAQ管理やログ管理などの管理画面用です。

## 動作確認手順

1. streamlit run app.py または既存の起動コマンドで起動
2. ログイン画面が表示されることを確認
3. demo / demo / demo でログイン
4. runtime_data/tenants/demo/ が作成されることを確認
5. customer-a など別会社IDでログイン設定を追加
6. FAQ、RAG、ログが会社別フォルダに分かれることを確認

## 修正ファイル

- runtime_main.py
- modules/settings_and_persistence.py
- modules/app_bootstrap.py
- modules/tenant_auth.py（新規）
