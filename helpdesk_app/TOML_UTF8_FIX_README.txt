# secrets.toml エラー修正

原因:
アップロードされた secrets.toml は TOML の書き方自体は正しいですが、ファイル文字コードが UTF-8 ではなく Shift_JIS/CP932 になっていました。
Streamlit の secrets.toml は UTF-8 前提のため、日本語を含む TENANT_USERS があると UnicodeDecodeError になります。

対応:
- helpdesk_app/.streamlit/secrets.toml を UTF-8 で追加しました。
- ログイン画面の説明文に「UTF-8で保存」を追記しました。

ローカルで使う場合:
1. helpdesk_app/.streamlit/secrets.toml をそのまま使ってください。
2. 編集する場合は VS Code などで「UTF-8」で保存してください。
3. Windowsメモ帳や古いエディタで編集して文字コードが ANSI/Shift_JIS になるとエラーになります。

設定例:
APP_MODE = "demo"
ENABLE_COMPANY_LOGIN = true
DEFAULT_TENANT_ID = "demo"
DEFAULT_LICENSE_TYPE = "trial"
DEFAULT_TRIAL_EXPIRE_DATE = "2026-05-24"
DEFAULT_LICENSE_ENABLED = true
TENANT_USERS = [
  "demo:demo:demo:デモユーザー:user",
  "c1:user1:user123:デモユーザー:user",
  "demo:admin:password:管理者:admin"
]
