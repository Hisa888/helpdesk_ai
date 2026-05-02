# FAQメモリ爆速版 更新内容

目的:
- 通常の問い合わせ検索時にDB/CSVへアクセスしない
- FAQ更新直後もDB/CSVを再読込せず、保存済みDataFrameから検索インデックスをメモリへ直接反映する

主な変更:
1. modules/faq_index_runtime.py
   - DataFrameから検索インデックスを作る _build_faq_index_from_df を追加
   - prime_faq_index_from_df を追加
   - FAQ保存直後に検索用 state を直接更新できるように変更

2. modules/faq_admin_panel.py
   - FAQ更新後に st.cache_resource.clear() / st.cache_data.clear() を使わない
   - 保存済みDataFrameから prime_faq_index_from_df を呼び、次回検索を即メモリ検索化

3. faq_io.py
   - DB保存後のCSVキャッシュ同期をバックグラウンド化
   - GitHub永続化もCSV同期後にバックグラウンドで実行
   - 画面操作・次回検索をCSV書き出しや通信で待たせない

環境変数:
- HELP_DESK_FAQ_ASYNC_CSV_SYNC=1 既定: CSV同期を非同期化
- HELP_DESK_FAQ_SYNC_CSV=1 既定: CSVキャッシュは残す
- HELP_DESK_FAQ_SYNC_CSV=0 にするとDBのみ保存になり、さらに速くなるがCSVキャッシュは更新されない

注意:
- 初回起動時とFAQ更新時だけインデックス作成時間が発生します
- 通常検索はメモリ上のDataFrame/TF-IDF行列を使うため、DB検索より速くなります
