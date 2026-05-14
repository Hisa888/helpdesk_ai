# 無料トライアル期限管理 DB版 追加内容

## 追加した内容

### 1. 会社単位管理
会社ID（tenant_id）ごとにライセンス情報を管理します。

追加DB:

`runtime_data/tenant_licenses.db`

追加テーブル:

`tenant_licenses`

主なカラム:

- tenant_id: 会社ID
- company_name: 会社名
- license_type: trial / standard など
- expire_date: 利用期限 yyyy-mm-dd
- enabled: 会社IDの有効/無効
- max_users: 利用人数上限
- allow_search_after_expired: 期限後も問い合わせ画面を使わせるか
- admin_locked_after_expired: 期限後に管理者機能をロックするか
- max_questions_after_expired: 期限後の問い合わせ回数上限用
- note: 備考
- updated_at: 更新日時

## 2. 期限前UI
期限前は画面上部に以下を表示します。

無料トライアル期間中
残り○日

## 3. 期限後UI
期限後は以下を表示します。

無料トライアル期間が終了しました
継続利用をご希望の場合は導入相談へ
[導入相談]

## 4. 完全停止ではない制御
期限後もアプリ全体を完全停止しません。

- 導入相談導線は表示
- 問い合わせ画面は表示
- 管理者機能はロック
- 営業KPIなどのデモ表示は抑制

## 5. 初回起動時の動き
会社IDのライセンス行がDBに存在しない場合、secrets.toml または環境変数の既定値をもとに、tenant_licensesへ初回登録します。

例:

```toml
DEFAULT_LICENSE_TYPE = "trial"
DEFAULT_TRIAL_EXPIRE_DATE = "2026-06-01"
DEFAULT_LICENSE_ENABLED = true
```

会社ごとに直接DBで変更する場合は、tenant_licensesテーブルのexpire_dateを変更してください。

