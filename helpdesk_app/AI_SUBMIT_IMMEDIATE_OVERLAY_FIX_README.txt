# AI回答中表示 即時表示改善

## 修正内容

質問を入力して Enter キー、または送信ボタンを押した瞬間から、ブラウザ側で
「AIが回答を作成しています」オーバーレイを表示するようにしました。

従来の Python 側表示だけだと、Streamlit の再描画タイミングによって一瞬しか見えない、
または処理開始直後に表示されない場合がありました。

## 変更ファイル

- helpdesk_app/modules/client_submit_overlay.py
  - 送信直後にブラウザ側で待機表示を出す専用モジュールを追加
- helpdesk_app/modules/chat_input_panel.py
  - st.chat_input 描画前に即時表示用の JavaScript を読み込むよう変更

## 効果

- Enterキーを押した瞬間に待機表示
- 送信ボタンを押した瞬間に待機表示
- PC/スマホ両対応
- 回答処理中に画面が固まったように見える問題を軽減

