# 追加質問の判定修正

## 修正内容

「アプリ」など、対象名だけの短い質問でFAQ一致度が高く出ても、すぐ回答せずに追加質問するよう修正しました。

例:
- 入力: アプリ
- 修正後: 何をしたいか、対象アプリ名、エラー/申請理由を確認
- 補足入力: インストール
- 検索用質問: アプリ インストール
- 回答: アプリインストール依頼のFAQを表示

## 主な修正ファイル

- helpdesk_app/modules/clarification_rules.py
- helpdesk_app/modules/query_flow_runtime.py
- helpdesk_app/modules/clarification_llm.py

## 確認済み

- 「アプリ」→追加質問になること
- 「アプリ インストール」→追加質問せず回答に進むこと
- 「アプリをインストールしたい」→追加質問せず回答に進むこと
- 「Wi-Fiがつながらない」→通常回答に進むこと
- Python構文チェック済み
