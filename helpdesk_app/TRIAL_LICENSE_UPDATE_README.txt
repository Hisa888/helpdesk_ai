# 無料トライアル期限・会社単位ライセンス管理 追加内容

## 追加したこと

既存の「アコーディオンボタン版」「スレッド機能なし版」は維持したまま、会社IDごとの無料トライアル期限チェックを追加しました。

### 期限前

画面上に以下を表示します。

- 無料トライアル期間中
- 残り○日

### 期限後

通常画面には進ませず、以下の案内画面を表示します。

- 無料トライアル期間が終了しました
- 継続利用をご希望の場合は導入相談へ
- 導入相談ボタン

## 追加ファイル

- `helpdesk_app/modules/trial_license.py`

## 修正ファイル

- `helpdesk_app/runtime_main.py`

## secrets.toml 設定例

`.streamlit/secrets.toml` に以下のように設定できます。

```toml
# 会社IDごとの期限設定
[TENANT_LICENSES]
demo = "trial:2026-06-01:true"
customer-a = "trial:2026-05-31:true"
customer-b = "standard::true"

# TENANT_LICENSES 未設定時のデフォルト期限
DEFAULT_LICENSE_TYPE = "trial"
DEFAULT_TRIAL_EXPIRE_DATE = "2026-06-01"
DEFAULT_LICENSE_ENABLED = true
```

## 書式

```text
会社ID = "ライセンス種別:期限日:有効フラグ"
```

例：

```toml
demo = "trial:2026-06-01:true"
```

- `trial` は無料トライアル扱い
- `standard` は期限表示なし
- 期限日は `YYYY-MM-DD`
- `true` は有効、`false` は停止

## 注意

期限切れ時は `st.stop()` ではなく、専用の期限切れ画面を表示して終了しています。
そのため、真っ白画面にはならず、導入相談へ自然につながります。
