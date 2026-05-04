FAQ検索精度・誤回答防止 修正内容

目的:
- 「起案書の書式はありますか？」で FAQ-000025 を優先ヒットさせる。
- 「システム導入するための申請書はどれですか？」などの自然文でも、該当するFAQを優先する。
- 高スコアでも候補差が小さい場合や個別語が合っていない場合は、嘘の自動回答を避けて「もしかしてこれですか？」候補表示に回す。

主な修正:
1. TF-IDF疎行列スコアの変換バグを修正
   - SciPy sparse matrix を必ず dense float 配列へ変換。
   - 環境差で検索結果が空になったり順位が崩れる問題を抑制。

2. 個別業務語の優先判定を追加
   - 起案書、念書、承諾書、サイトアクセス許可、システム導入など。
   - 「申請書」「書式」「資料」だけでなく、個別語が一致するFAQを強く優先。

3. 汎用申請書FAQの誤採用を抑制
   - ユーザー質問に個別語があるのに候補FAQにその個別語が無い場合は減点。

4. 「もしかしてこれ？」への安全ガードを追加
   - 高スコアでも上位候補の差が小さい場合は、自動回答せず候補表示に回せるようにしました。
   - 嘘の回答を避けるための業務向け安全仕様です。

確認済み:
- 起案書の書式はありますか？ → FAQ-000025
- システム導入するための申請書はどれですか？ → システム導入FAQ
- サイトアクセス許可の申請書はどれですか？ → サイトアクセス許可FAQ

修正ファイル:
- helpdesk_app/modules/search_runtime.py
- helpdesk_app/modules/query_flow_runtime.py
- helpdesk_app/modules/faq_answer_flow_runtime.py
- helpdesk_app/modules/app_runtime_services.py
- helpdesk_app/modules/app_runtime_contexts.py
- helpdesk_app/modules/app_surface_runner.py
- helpdesk_app/modules/main_screen_layout.py
- helpdesk_app/modules/chat_interaction_runtime.py
