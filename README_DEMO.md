# 情シス問い合わせAI（副業デモ用）

FAQ（根拠）を参照して回答する、社内ヘルプデスク向けのデモアプリです（RAG + LLM）。

## できること
- FAQから最も近い回答を提示（根拠表示 + 一致度% + 一致度バー）
- 一致度が低い場合は「該当なし」へ誘導し、問い合わせテンプレを提示
- 「該当なし」ログをCSVに蓄積（Streamlit画面からCSV/ZIPでダウンロード可能）
- おすすめ質問ボタン（初見でも迷わない）

## ファイル構成（例）
- `app.py` … Streamlitアプリ本体
- `services/` … 認証・LLMルータ等
- `faq.csv` … FAQデータ（`question,answer,category` 列を推奨）
- `requirements.txt` … 依存パッケージ

## Streamlit Cloud デプロイ手順
1. このリポジトリをGitHubにPush
2. Streamlit Community Cloudで `Create app`
3. Repository / Branch / Main file を指定  
   - Repository: `あなたのユーザー名/リポジトリ名`
   - Branch: `main`
   - Main file path: `app.py`

## Secrets（必須）
Streamlit Cloud → Settings → Secrets に以下を設定（TOML形式）:

```toml
LLM_PROVIDER="groq"
GROQ_API_KEY="YOUR_API_KEY"
GROQ_MODEL="llama-3.1-8b-instant"
ADMIN_PASSWORD="任意（管理者用）"
```

## デモの見せ方（おすすめ）
- まず「おすすめ質問」をクリックして動作を見せる
- 「参照したFAQ（根拠）」を開き、根拠と一致度を説明する
- わざとFAQに無い質問をして「該当なしテンプレ」と「ログ蓄積→DL」を見せる

## 注意
- APIキーは絶対にGitHubへコミットしない（Secretsにのみ保存）
- 既に公開してしまったキーは必ずRevokeして作り直す
