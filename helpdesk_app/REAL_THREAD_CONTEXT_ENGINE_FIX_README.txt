# 本物の問い合わせスレッド管理UI＋文脈検索 修正

## 修正概要

今回の修正では、見た目だけのスレッド管理ではなく、検索ロジック側にもスレッド文脈を反映しました。

## 追加・改善内容

1. ヘッダーにも「＋ 新規問い合わせを開始」ボタンを追加
   - 左メニューを探さなくても新しい問い合わせを開始できます。

2. スレッド単位で会話履歴を保持
   - `st.session_state.inquiry_threads`
   - `st.session_state.current_thread_id`
   - `last_parent_question`
   - `last_parent_faq_id`
   - `last_parent_answer`

3. 補足質問の検索ロジックを改善
   - 「やり方」
   - 「どうやる」
   - 「詳しく」
   - 「分からない」
   - 「手順」
   などを同一スレッドの追加質問として扱います。

4. 親FAQの同じ回答を繰り返さない処理を追加
   - 親FAQ配下の子FAQがある場合は、子FAQを優先回答します。
   - 子FAQが未登録でも、Excelの代表的な詳細手順は直接回答します。

## 確認例

1. 「Excelが起動しない」と質問
2. 続けて「セーフモード起動ってどうやるの？」と質問
3. 同じ親FAQ回答ではなく、以下のような具体手順が表示されます。

```text
Windowsキー + R
excel /safe
OK
```

## 新規問い合わせの開始方法

画面中央上部の「＋ 新規問い合わせを開始」または左サイドバーの「＋ 新規問い合わせ」を押します。

## 注意

FAQに子FAQを登録すると、より正確に回答できます。
以下の列に対応しています。

- FAQ_ID
- PARENT_ID / parent_id / 親FAQ_ID
- FAQ_TYPE / faq_type / 種別
- DETAIL_KEYWORDS / detail_keywords / 詳細キーワード
- FOLLOWUP_LABEL / followup_label / 表示ラベル
