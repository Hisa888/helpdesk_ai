# 検索高速化対応（FAQ優先・RAG/LLM遅延実行）

## 修正内容

検索時の体感速度を上げるため、以下を修正しました。

1. FAQで十分回答できる場合は、社内ドキュメントRAG検索を実行しない
   - これまではFAQ候補がある場合でも、先にRAG検索が走る構造がありました。
   - 修正後は、FAQスコアが低い/曖昧な場合だけRAG検索します。

2. FAQ自動回答時は、原則FAQ回答をそのまま返す
   - これまではFAQ一致後もLLM回答生成へ進む場合があり、遅くなる原因でした。
   - 修正後は、FAQに十分一致した場合はLLMを呼ばず即回答します。

3. SentenceTransformerの意味検索をデフォルトOFF
   - 意味検索は精度補助には有効ですが、初回ロード/埋め込み生成が重いです。
   - 必要な場合だけ `semantic_enabled = true` 相当の設定で有効化してください。

4. FAQ候補プールの初期値を軽量化
   - 検索補正対象を絞り、全件に近い重い補正が走りにくくしました。

## 追加された設定キー（任意）

既存設定に入れなくても動きます。

- `doc_rag_always_compare`
  - true: FAQが強い場合でもRAGと毎回比較
  - false: FAQが弱い/曖昧な時だけRAG検索（高速・推奨）

- `faq_llm_answer_enabled`
  - true: FAQ回答をLLMで整形する
  - false: FAQ回答をそのまま返す（高速・推奨）

- `faq_llm_trigger_max_score`
  - FAQスコアがこの値以下の時だけLLM整形を許可
  - 例: 0.55

- `semantic_enabled`
  - true: SentenceTransformer意味検索を有効化
  - false: TF-IDF + 文字n-gram中心で高速検索（推奨）

## 変更ファイル

- `helpdesk_app/modules/query_flow_runtime.py`
- `helpdesk_app/modules/search_runtime.py`
- `helpdesk_app/modules/faq_index_runtime.py`

## 期待効果

- FAQで回答できる質問は、RAG/LLMを呼ばずに返すため高速化
- RAG文書が多い環境でも、通常FAQ検索の体感速度が落ちにくい
- ローカルLLM/Ollama/Groqの応答待ちによる遅延を回避
