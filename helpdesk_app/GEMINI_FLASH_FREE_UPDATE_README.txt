# Gemini Flash Lite 無料枠対応

## 修正内容

- 管理画面の「LLM切替設定」に `Gemini Flash（無料枠・推奨）` を追加しました。
- 初期LLMを `gemini` にしました。
- 初期Geminiモデルを `gemini-2.5-flash-lite` にしました。
- `GEMINI_API_KEY` を Streamlit Secrets または環境変数から読み込みます。
- Gemini呼び出しは `requests` によるREST方式のため、追加SDKは不要です。
- Gemini接続失敗時は既存LLM処理へフォールバックします。

## Streamlit Cloud Secrets設定

```toml
GEMINI_API_KEY="AIzaSyxxxxxxxxxxxxxxxxxxxxxxxx"
```

## 管理画面での確認

管理者ログイン後、`LLM切替設定` を開き、
`Gemini Flash（無料枠・推奨）` を選択して保存してください。
