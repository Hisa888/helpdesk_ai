# 社内ドキュメントRAG管理 metadata表示修正

## 修正内容
- RAG登録時に filename/type/uploaded_at/uploaded_by/path を manifest.json に保存
- 旧データで manifest.files が壊れていても chunks.json の source_name/source_type から管理一覧を復元
- 管理一覧が「・」や空欄になる問題を修正
- 削除ボタンの戻り値を panel 側に合わせて dict 形式へ統一
- build_document_rag_index(uploaded_by=...) を受け取れるように修正

## 注意
既に登録済みの旧RAGデータも chunks.json から復元して表示します。
ただし登録者や取込日が旧データに無い場合は「管理者」または manifest の更新日時を表示します。
