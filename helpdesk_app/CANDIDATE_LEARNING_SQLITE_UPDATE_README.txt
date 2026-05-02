# 学習ログSQLite保存 追加パッチ

## 追加内容
- 「もしかしてこれ？」候補クリック時に、CSVだけでなく SQLite にも保存します。
- 保存先DB: runtime_data/helpdesk.db
- 追加テーブル: candidate_learning

## 保存される項目
- timestamp
- user_question
- selected_faq_id
- selected_question
- score
- category

## 検索時の利用順
1. SQLite の candidate_learning テーブル
2. 既存の logs/candidate_learning_YYYYMMDD.csv
3. セッション内の一時ログ

## 注意
- SQLite DBファイルが残る環境なら、アプリ再起動後も学習結果が残ります。
- Streamlit Cloudなど一時ファイルが消える環境では、DBファイル自体も消える可能性があります。
  本番では AWS / 自社サーバー / 永続ディスク / GitHub退避などを推奨します。
