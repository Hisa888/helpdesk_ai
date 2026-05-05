# 回答後の追加情報欄 常時表示修正

## 修正内容

回答が誤っている可能性に備えて、FAQ回答・候補選択後の回答・社内ドキュメントRAG回答・該当なし案内のいずれでも、回答後に画面下側へ「追加情報を記録（任意）」欄を表示するようにしました。

## 表示位置

回答 → 回答の根拠を見る → 追加情報を記録（任意）

## 表示状態

「追加情報を記録（任意）」は初期状態で閉じた状態です。

## 対象ファイル

- helpdesk_app/modules/query_flow_runtime.py
- helpdesk_app/modules/chat_interaction_runtime.py
