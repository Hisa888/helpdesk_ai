# 検索速度改善パッチ

検索が遅くなる主な原因を確認し、速度優先で修正しました。

## 修正内容
- FAQ採用時はLLM回答生成を初期OFFにしました。
  - FAQの回答欄をそのまま返すため高速です。
  - LLM整形が必要な場合のみ search_settings.json で llm_answer_enabled=true にします。
- FAQスコアが十分高い場合は、RAG検索を毎回実行しないようにしました。
  - RAGはFAQ候補が弱い場合のみ実行します。
  - 常時比較したい場合のみ always_compare_doc_rag=true にします。
- 意味検索 semantic_enabled の初期値をOFFにしました。
  - sentence-transformers の初回ロードや埋め込み生成による待ち時間を防ぎます。
- LLM再ランキング/スレッドカテゴリ補正を速度優先でOFF/無効化しました。
- __pycache__ をZIPから除外しました。

## 速度優先の推奨設定
```json
{
  "semantic_enabled": false,
  "llm_answer_enabled": false,
  "always_compare_doc_rag": false,
  "llm_rerank_enabled": false
}
```

既存の無料トライアル期限表示、会社IDログイン、アコーディオン管理画面は維持しています。
