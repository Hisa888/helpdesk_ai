# UI配色初期化エラー修正

## 修正内容

「UI配色設定」内の「UI配色を初期値に戻す」を押した際に、以下のエラーが出る問題を修正しました。

```
st.session_state.ui_sidebar_bg_start cannot be modified after the widget with key ui_sidebar_bg_start is instantiated.
```

## 原因

Streamlitでは、`st.color_picker` や `st.text_input` に指定した widget key は、
そのウィジェット生成後に `st.session_state[widget_key] = ...` で直接変更できません。

## 対応

初期化ボタン押下時に widget key を直接書き換えず、保存済みテーマ設定のみ初期値へ戻し、
`st.rerun()` 後に初期値を再読み込みする方式へ変更しました。

## 既存機能

- アコーディオンボタン版は維持
- スレッドなし版は維持
- 無料トライアル表示は維持
- TENANT_USERS 認証は維持
