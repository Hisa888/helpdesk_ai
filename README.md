# 情シス問い合わせAI v14 完全完成版

## 起動方法（ローカル）
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Streamlit Cloud に上げる場合
1. このZIPを展開
2. GitHub リポジトリへアップロード
3. `app.py` をメインファイルに指定

## 任意設定
- `ADMIN_PASSWORD` : 管理者パスワード
- `GROQ_API_KEY` : Groq APIキー
- `GROQ_MODEL` : Groqモデル名（省略可）
- `COMPANY_NAME` / `LOGO_PATH` / `CONTACT_URL` / `CONTACT_EMAIL`
- `PERSIST_MODE=github` + GitHub系 secrets で永続化

## 初期値
- 管理者パスワード未設定時: `admin123`

## 同梱内容
- フル機能版 `app.py`
- FAQ管理（CSV/Excel）
- FAQ自動生成
- PDF出力
- ログ見える化
- GitHub永続化対応
