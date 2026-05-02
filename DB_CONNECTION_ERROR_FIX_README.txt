DB化後の Connection error 対策

原因候補:
SQLiteのWALモードにより runtime_data/helpdesk.db-wal / helpdesk.db-shm が頻繁に更新され、
Streamlitのファイル監視が反応して接続が切れる場合があります。

修正内容:
- helpdesk_app/faq_db.py の SQLite 接続を WAL ではなく DELETE ジャーナル方式に変更
- DB接続 timeout=30 を追加
- FAQ保存時は SQLite DB を正本、faq.csv を検索・ダウンロード用キャッシュとして維持

確認コマンド:
python -m compileall helpdesk_app
streamlit run app.py

既に runtime_data/helpdesk.db-wal / runtime_data/helpdesk.db-shm が残っている場合は、
Streamlitを停止してから削除してOKです。
