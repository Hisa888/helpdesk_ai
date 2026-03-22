# 情シス問い合わせAI v14 完全完成版

このZIPは **そのまま起動できる実行構成** です。

- `app.py` : 現在のフル機能版アプリ本体
- `services/auth.py` : 管理者パスワード認証
- `services/llm_router.py` : Groq API連携（未設定時は安全なフォールバック）
- `runtime_data/faq.csv` : 初期FAQデータ
- `runtime_data/search_settings.json` : 初期閾値設定
- `runtime_data/logs/` : ログ保存先

補助的に `core/ faq/ ai/ logs/ ui/ admin/ pdf/` ディレクトリも用意しています。
今後 app.py の機能を段階的に分割していくための受け皿です。
