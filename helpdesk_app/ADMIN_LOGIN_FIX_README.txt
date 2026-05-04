# 管理者ログイン修正

## 修正内容

管理者ログインID/パスワードの読み取りを強化しました。

対応形式:

1. 1人用

```toml
ADMIN_LOGIN_ID = "admin"
ADMIN_PASSWORD = "admin0123"
```

2. 複数管理者用

```toml
ADMIN_USERS = "sato:password1,tanaka:password2,admin:admin0123"
```

3. 複数管理者用（配列）

```toml
ADMIN_USERS = ["sato:password1", "tanaka:password2", "admin:admin0123"]
```

4. 複数管理者用（TOMLテーブル）

```toml
[ADMIN_USERS]
sato = "password1"
tanaka = "password2"
admin = "admin0123"
```

## 互換対応

過去の設定名も読めるようにしました。

- ADMIN_LOGIN_ID
- ADMIN_USER_ID
- ADMIN_ID
- ADMIN_USERNAME
- ADMIN_PASSWORD
- ADMIN_PASS
- ADMIN_PWD
- ADMIN_ADMIN_PASSWORD
- ADMIN_PW

## Streamlit Cloud の注意

Streamlit Cloud では、`.streamlit/secrets.toml` ではなく、アプリの Settings → Secrets に同じ内容を登録してください。
登録後はアプリを再起動してください。

## 更新者

FAQを追加・更新・削除した場合、更新者にはログイン時に入力したログインIDが保存されます。
