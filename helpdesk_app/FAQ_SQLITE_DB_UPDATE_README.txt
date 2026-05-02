# FAQ SQLite DB化対応

## 対応内容

FAQの内部保存を SQLite に変更しました。

- 正本DB: runtime_data/helpdesk.db
- 既存互換キャッシュ: runtime_data/faq.csv

既存の検索処理・Excel/CSVダウンロード・FAQ一括取込を壊さないため、
アプリ内部では SQLite を正本として使いながら、faq.csv も自動同期します。

## 追加・変更ファイル

- helpdesk_app/faq_db.py
  - SQLiteの作成、読込、保存、CSVキャッシュ同期

- helpdesk_app/faq_io.py
  - runtime_data/faq.csv 読込時は SQLite を優先
  - FAQ保存時は SQLite + CSVキャッシュの両方を更新
  - 既存faq.csvからhelpdesk.dbを初期作成する initialize_faq_database を追加

- helpdesk_app/modules/app_runtime_services.py
  - 起動時に既存faq.csvからhelpdesk.dbを自動初期化

- helpdesk_app/modules/admin_faq_generation_utils.py
  - マニュアル自動FAQ化/FAQ案追記でもDB保存経由に変更

## 起動確認

```powershell
python -m compileall helpdesk_app
streamlit run app.py
```

起動後、以下が作成されていればOKです。

```text
runtime_data/helpdesk.db
```

## 運用ルール

今後も管理者はExcel/CSVでFAQを取り込みできます。
ただし、内部の正本はDBになります。
faq.csvは検索・ダウンロード互換用のキャッシュとして残します。

## テスト観点

1. アプリ起動後、runtime_data/helpdesk.db が作成される
2. FAQを1件追加して、既存FAQが消えない
3. FAQを更新して、更新日・更新者がログインIDで入る
4. FAQを削除して、対象行だけ消える
5. 再起動してもFAQが残る
