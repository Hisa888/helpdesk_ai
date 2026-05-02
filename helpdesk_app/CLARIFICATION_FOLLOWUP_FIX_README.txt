追加情報入力の表示・検索改善 修正メモ

修正目的:
- 「アプリ」と入力後、追加質問に対して「インストール」と入力しても回答が表示されない/入力が反映されていないように見える問題を改善。

修正内容:
1. 追加質問への回答時、検索用の質問を「元の質問 + 補足情報」で結合するように修正。
   例: 「アプリ」→補足「インストール」 = 検索用「アプリ インストール」
2. チャット履歴にも「元の質問」と「補足情報」を表示するように修正。
   例:
   アプリ

   補足情報：インストール
3. 検索時に「補足情報」というラベル文字が混ざらないように修正。
4. アプリ/ソフト/インストール/導入/申請系の検索ヒントを追加。
5. 回答処理中に例外が出た場合でも、画面が無反応にならないようにフォールバック回答を表示。

修正対象:
- helpdesk_app/modules/chat_interaction_runtime.py
- helpdesk_app/modules/clarification_state.py
- helpdesk_app/modules/clarification_rules.py
- helpdesk_app/modules/faq_answer_flow_runtime.py
- helpdesk_app/modules/search_runtime.py
