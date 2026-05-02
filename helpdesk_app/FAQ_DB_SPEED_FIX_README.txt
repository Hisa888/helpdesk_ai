# FAQ DB高速化パッチ

## 修正内容

### 1. SQLite接続設定を高速化
`helpdesk_app/faq_db.py` のSQLite接続に以下を追加しました。

- `PRAGMA journal_mode=WAL`
- `PRAGMA synchronous=NORMAL`
- `PRAGMA temp_store=MEMORY`
- `PRAGMA cache_size=-64000`
- `PRAGMA busy_timeout=30000`

※ ローカルStreamlitで `.db-wal` / `.db-shm` のファイル監視が原因で不安定な場合は、環境変数で戻せます。

```bash
HELP_DESK_SQLITE_WAL=0
```

### 2. 保存方式を「全件DELETE → 全件INSERT」から変更
以前はFAQ保存時にDBを一度全削除してから全件INSERTしていました。
今回から以下の方式に変更しています。

- FAQ_IDが存在する行：UPSERTで更新
- FAQ_IDが新しい行：INSERTで追加
- 今回のFAQ一覧に存在しないFAQ_ID：削除

これにより、既存DBを毎回作り直さずに同期できます。

### 3. DB読み込みキャッシュを追加
同じDBを短時間に何度も読み込まないよう、DBの更新日時・サイズが変わらない場合はDataFrameキャッシュを再利用します。

- デフォルトTTL：30秒
- 変更したい場合：`HELP_DESK_FAQ_DB_CACHE_TTL`

```bash
HELP_DESK_FAQ_DB_CACHE_TTL=10
```

### 4. CSV→DB同期方式を改善
`runtime_data/faq.csv` は既存のダウンロード・Git永続化互換のためキャッシュとして残します。
検索・通常読み込みはSQLiteを正本として使います。

また、Git反映や手動配置で `faq.csv` の方がDBより新しい場合のみ、起動時にCSVからDBへ同期します。

## 修正ファイル

- `helpdesk_app/faq_db.py`

## 既存機能について

以下は維持しています。

- FAQ_IDベースの管理
- 既存データを消さない差分反映
- 更新日・更新者の自動設定
- CSV/Excelダウンロード互換
- runtime_data/faq.csv のキャッシュ出力
