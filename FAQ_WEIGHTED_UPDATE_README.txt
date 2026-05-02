FAQ重み付け検索 改修メモ

追加したFAQ項目:
- question: ユーザーが実際に入力する質問文
- answer: 短く結論→手順で書いた回答
- intent: 質問の意味・目的
- keywords: 言い換え、表記ゆれ、検索語
- category: 分類

既存の answer_format は、text / markdown / html 表示を壊さないため残しています。

管理画面の「検索精度設定」に、下記の項目別重みを追加しました。
- question_weight
- answer_weight
- intent_weight
- keywords_weight
- category_weight

初期値:
question=3.0 / intent=2.5 / keywords=2.0 / category=1.0 / answer=0.5

試験データ:
- faq.csv
- runtime_data/faq.csv
- helpdesk_app/test_documents/faq_weighted_test_data.csv

動作確認例:
- パスワード忘れた
- ログインできない
- VPNつながらない
- メール見れない
- プリンタ印刷できない
- PC重い
- 共有フォルダ入れない
