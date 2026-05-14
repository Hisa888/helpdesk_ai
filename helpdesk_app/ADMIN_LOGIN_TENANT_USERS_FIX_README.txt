# 管理者ログイン修正（TENANT_USERS対応）

## 修正内容

会社IDログインを有効にしている場合でも、左サイドバーの「管理者」ログインで `TENANT_USERS` の管理者ユーザーを使えるようにしました。

今回の設定では以下で管理者ログインできます。

```toml
TENANT_USERS = [
  "demo:demo:demo:デモユーザー:user",
  "demo:admin:password:管理者:admin",
  "owner:owner:change_me:運営管理者:owner"
]
```

## demo会社の管理者ログイン

- ログインID: `admin`
- 管理者パスワード: `password`

`DEFAULT_TENANT_ID = "demo"` または会社ログイン後の会社IDが `demo` の場合、上記でログインできます。

## 追加修正

会社IDログイン画面で role が `admin` / `owner` / `manager` のユーザーとしてログインした場合、管理者状態 `is_admin` も同時に有効化するよう修正しました。

これにより、`demo / admin / password` で会社ログインした場合も管理者メニューが表示されます。
