# 親FAQ → 子FAQ 機能追加メモ

## 追加した機能

FAQを「親FAQ」と「子FAQ（詳細手順）」に分けられるようにしました。

例:
- 親FAQ: Excelが起動しない
- 子FAQ: Excelをセーフモードで起動する方法
- 子FAQ: Excelのアドオンを無効化する方法
- 子FAQ: Office修復を実行する方法

親FAQを回答したあと、ユーザーが「やり方が分からない」「詳しく」「セーフモードの方法」などと聞くと、
同じ親FAQを繰り返さず、直前の親FAQに紐づく子FAQだけを検索して詳細手順を回答します。

## 追加したFAQ列

Excel/CSVアップロード、DB保存、FAQエクスポートに以下の列を追加しました。

| 日本語列名 | 内部列名 | 内容 |
|---|---|---|
| 親FAQ_ID | parent_id | 子FAQの場合、親FAQのFAQ_IDを入れます。親FAQは空欄でOKです。 |
| FAQ種別 | faq_type | parent / child を任意で入れます。空欄でも動きます。 |
| 詳細キーワード | detail_keywords | セーフモード、アドオン、無効化、修復など、補足質問で拾いたい語を入れます。 |
| 詳細ボタン名 | followup_label | 親FAQ回答後に表示する詳細ボタン名です。 |

## FAQデータ例

| FAQ_ID | 親FAQ_ID | FAQ種別 | 質問 | 回答 | 詳細キーワード | 詳細ボタン名 |
|---|---|---|---|---|---|---|
| FAQ-000100 |  | parent | Excelが起動しない | まずセーフモード起動、アドオン無効化、Office修復を確認してください。 | Excel,起動しない,セーフモード,アドオン,修復 |  |
| FAQ-000101 | FAQ-000100 | child | Excelをセーフモードで起動する方法 | 1. Windowsキー+Rを押す\n2. excel /safe と入力\n3. Enterを押す | セーフモード,やり方,方法,起動 | セーフモードのやり方 |
| FAQ-000102 | FAQ-000100 | child | Excelのアドオンを無効化する方法 | 1. Excelを開く\n2. ファイル→オプション→アドイン\n3. COMアドインを管理から無効化 | アドオン,無効化,やり方,方法 | アドオン無効化の方法 |

## 動作イメージ

1. ユーザー: Excelが起動しないです
2. AI: 親FAQを回答し、下部に「詳しい手順を見る」ボタンを表示
3. ユーザー: やり方が分からない / セーフモードのやり方
4. AI: 直前の親FAQ配下の子FAQだけを検索して、該当する詳細手順を回答

## 変更ファイル

- helpdesk_app/faq_io.py
  - FAQ列定義、Excel/CSVインポート・エクスポートの列追加
- helpdesk_app/faq_db.py
  - SQLiteのFAQテーブルに親子FAQ用カラム追加
- helpdesk_app/modules/search_runtime.py
  - 子FAQ取得、親FAQ回答後の詳細案内生成を追加
- helpdesk_app/modules/query_flow_runtime.py
  - 補足質問判定、直前親FAQ配下の子FAQ検索を追加
- helpdesk_app/modules/answer_panel.py
  - 詳しい手順を見るボタンを追加
- helpdesk_app/modules/chat_history_panel.py
  - 履歴再描画時にも詳細ボタンを保持
- helpdesk_app/modules/chat_interaction_runtime.py
- helpdesk_app/modules/main_screen_layout.py
- helpdesk_app/modules/app_surface_runner.py
- helpdesk_app/modules/app_runtime_contexts.py
  - 追加関数の受け渡し対応

## 既存FAQへの影響

追加列が空欄の場合は、従来通り1問1答FAQとして動作します。
既存FAQを消す変更ではありません。
