# AI回答中ステータスバー追加

## 修正内容
質問送信後、AIがFAQ・社内ナレッジを検索して回答を作成している間に、画面下部へ固定のステータスバーを表示するようにしました。

## 目的
Streamlitの再描画中に画面が白っぽくなり、利用者が「固まった」「止まった」と感じる問題を軽減します。

## 表示内容
- AIが回答を作成しています
- FAQ・社内ナレッジを検索中です。数秒お待ちください。
- 動きのある進行バー

## 対応画面
- PC表示
- スマホ表示

## 修正ファイル
- helpdesk_app/modules/chat_interaction_runtime.py
- helpdesk_app/modules/app_bootstrap.py
