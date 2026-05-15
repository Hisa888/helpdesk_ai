# FAQ検索indexキャッシュ / RAG index保存方式 高速化対応

## 対応内容

### 1. FAQ検索indexを永続キャッシュ化
- FAQ検索用の TF-IDF index を毎回作り直さないようにしました。
- FAQファイル更新日時・サイズ・検索項目重みが変わらない場合、保存済みindexを再利用します。
- Streamlit再起動後も `.search_index.pkl` を再利用できるため、初回検索の待ち時間を軽減します。

### 2. FAQ更新時のキャッシュ更新
- FAQを保存・反映した直後に、メモリ上の検索indexだけでなく、ディスク上の検索indexも更新します。
- 古い Streamlit cache が残らないよう、関連cacheをクリアする処理も追加しました。

### 3. RAG検索indexを保存方式に変更
- 社内ドキュメントRAGの TF-IDF index を `runtime_data/doc_rag/tfidf_index.pkl` に保存する方式へ変更しました。
- 以前はRAG検索のたびに `fit_transform` していましたが、今後は原則としてアップロード・反映時に一度だけ作成します。
- 旧データでindexが無い場合も、初回検索時に自動生成して保存します。

### 4. RAG削除・全削除時のindex整合性対応
- ドキュメント削除時、チャンクとindexの件数ズレを防ぐため、保存済みRAG indexを削除します。
- 次回反映または検索時に再生成されます。

## 期待効果
- FAQ初回検索の待ち時間軽減
- RAG検索時の毎回index作成を回避
- ドキュメント数・チャンク数が増えた場合の体感速度改善

## 修正ファイル
- `helpdesk_app/modules/faq_index_runtime.py`
- `helpdesk_app/modules/document_rag_runtime.py`
