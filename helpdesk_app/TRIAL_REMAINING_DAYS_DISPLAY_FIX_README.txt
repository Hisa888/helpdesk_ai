# 無料トライアル期限表示 修正

## 修正内容

`DEFAULT_TRIAL_EXPIRE_DATE` を `secrets.toml` に設定しても、既存の `runtime_data/tenant_licenses.db` に同じ会社IDの行が空の状態で残っている場合、DBが優先されて期限が表示されない問題を修正しました。

## 対応

- DBに会社IDの行が存在しても `expire_date` が空の場合は、`DEFAULT_TRIAL_EXPIRE_DATE` で自動補完します。
- サイドバーにも「無料トライアル期間中 / 残り○日」を表示します。
- 期限切れの場合はサイドバーにも「無料トライアル終了」を表示します。
- ログアウト時にライセンス表示用のセッション情報もクリアします。

## 設定例

```toml
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
```

## 注意

既にDBに `expire_date` が入っている場合は、DB側の値を優先します。
会社ごとに期限を変える場合は `runtime_data/tenant_licenses.db` の `tenant_licenses.expire_date` を変更してください。
