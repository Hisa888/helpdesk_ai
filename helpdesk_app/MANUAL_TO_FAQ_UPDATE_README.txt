マニュアル → FAQ自動生成 強化版

追加・修正内容:
1. Excel / Word / PDF / Text / Markdown / Wiki本文のアップロードに対応
2. Excelは全シートを読み込み、以下を自動判定
   - question / answer 列: そのままFAQ候補化
   - 項目 / 内容 / 手順 / 説明 列: 行単位でFAQ案を生成
   - その他の表: 全セルを「列名: 値」の文章へ変換してAIに渡す
3. 処理フローを管理画面に明示
   ドキュメント読込 → 文章化 → 内容理解 → Q&A生成 → 管理者確認 → FAQ反映
4. FAQ反映前に管理者確認チェックを追加
5. LLM失敗時も簡易FAQ候補を生成するフォールバックを強化

主な修正ファイル:
- helpdesk_app/modules/manual_faq_generation_utils.py
- helpdesk_app/modules/manual_faq_generation_panel.py
- helpdesk_app/modules/admin_complete_sections.py
- helpdesk_app/admin_menu_complete.py
- helpdesk_app/modules/app_runtime_services.py
- helpdesk_app/modules/app_surface_runner.py
- helpdesk_app/modules/app_runtime_contexts.py

確認方法:
1. 管理者ログイン
2. 「📚 マニュアル → FAQ自動生成」を開く
3. Excel / Word / PDF / txt / md をアップロード
4. 「マニュアルからFAQ案を生成」
5. 「文章化した資料本文を確認」で読込結果を確認
6. FAQ案を編集
7. 「管理者確認済み」にチェック
8. faq.csvへ追記
