# 無料トライアル期限の反映修正

## 修正内容

`DEFAULT_TRIAL_EXPIRE_DATE` を変更しても、既存の `runtime_data/tenant_licenses.db` に残っている古い期限日が優先され、画面上は以前の期限で表示される問題を修正しました。

## 変更後の動き

- `DEFAULT_TENANT_ID` とログイン中の会社IDが一致する場合、`.streamlit/secrets.toml` の `DEFAULT_TRIAL_EXPIRE_DATE` を優先します。
- DBに古い期限日が残っていても、起動時に secrets.toml の期限日へ同期します。
- サイドバーの無料トライアル表示に期限日も表示します。
- 期限切れの場合は、期限切れ画面を表示します。

## 例

```toml
DEFAULT_TENANT_ID = "demo"
DEFAULT_TRIAL_EXPIRE_DATE = "2026-05-09"
```

会社ID `demo` でログインしている場合、DBに `2026-05-24` が残っていても `2026-05-09` が優先されます。
