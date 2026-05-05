# 完全版：会社IDログイン + company_id分離 + 候補ボタン回答表示

## 追加・修正内容

1. アプリ起動直後に会社ログイン画面を表示
   - 会社ID
   - ログインID
   - パスワード

2. 会社IDごとにデータを分離
   - FAQ: runtime_data/tenants/{会社ID}/faq.csv
   - DB:  runtime_data/tenants/{会社ID}/helpdesk.db
   - RAG: runtime_data/tenants/{会社ID}/doc_rag
   - ログ: runtime_data/tenants/{会社ID}/logs
   - UI設定/検索設定/LLM設定も会社別

3. 初回起動時の既存FAQ保護
   - ルートの faq.csv が存在し、会社別 faq.csv が未作成の場合のみコピー
   - 既存データは削除しない

4. 会社別ログインユーザー管理
   .streamlit/secrets.toml に以下を設定できます。

   例1：文字列形式
   TENANT_USERS = "demo:demo:demo:デモ管理者:admin, customer-a:sato:pass123:佐藤:user"

   例2：配列形式
   TENANT_USERS = [
     "demo:demo:demo:デモ管理者:admin",
     "customer-a:sato:pass123:佐藤:user",
     "customer-a:admin:adminpass:顧客A管理者:admin"
   ]

   例3：テーブル形式
   [TENANT_USERS]
   "demo/demo" = "demo"
   "customer-a/sato" = "pass123"

5. 管理者権限
   - role に admin / owner / manager を指定すると、既存の管理者画面も利用できます。
   - 初期値 demo / demo / demo は admin 扱いです。

6. 「もしかしてこれですか？」ボタン修正
   - 候補ボタンを押すと、再検索ではなく選択FAQの回答を直接表示します。
   - しきい値や曖昧判定で再び候補表示に戻る問題を回避しました。

## Streamlit Cloud の起動ファイル

このZIPにはルート直下に app.py を追加しています。
Streamlit Cloud の Main file path は以下を推奨します。

app.py

既存設定で helpdesk_app/__main__.py を指定していても動作します。

## 初期ログイン

会社ID: demo
ログインID: demo
パスワード: demo

本番では必ず TENANT_USERS を設定し、初期パスワードを変更してください。
