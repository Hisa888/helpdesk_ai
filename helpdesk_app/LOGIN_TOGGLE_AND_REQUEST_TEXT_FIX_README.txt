# ログインあり/なし切替 + 依頼内容ラベル修正

## 1. ログイン画面の切替

`.streamlit/secrets.toml` または Streamlit Cloud の Secrets に以下を設定します。

```toml
# ログイン画面あり（本番・顧客提供向け）
ENABLE_COMPANY_LOGIN = true

# ログイン画面なし（開発・デモ向け）
# ENABLE_COMPANY_LOGIN = false
```

## 2. ログインなしの場合

`ENABLE_COMPANY_LOGIN = false` の場合は、ログイン画面を表示せずに以下の会社として自動ログインします。

```toml
ENABLE_COMPANY_LOGIN = false
DEFAULT_TENANT_ID = "demo"
DEFAULT_LOGIN_ID = "demo"
DEFAULT_TENANT_ROLE = "admin"
```

会社別データは従来通り以下に分離されます。

```text
runtime_data/tenants/demo/
```

## 3. ログインありの場合

```toml
ENABLE_COMPANY_LOGIN = true
TENANT_USERS = "demo:demo:demo:デモ管理者:admin"
```

## 4. 文言修正

「追加情報を記録（任意）」欄の `エラー内容（任意）` を `依頼内容（任意）` に変更しました。

保存ログには新しい `request_text` を追加し、既存互換のため `error_text` も残しています。
