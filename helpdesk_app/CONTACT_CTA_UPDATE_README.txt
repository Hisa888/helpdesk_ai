導入導線（CTA）追加内容

追加ファイル:
- helpdesk_app/modules/contact_cta_panel.py

修正ファイル:
- helpdesk_app/runtime_main.py

表示内容:
- ヒーロー下に「導入相談」CTAパネルを追加
- 無料相談ボタン
- メール文面作成ボタン
- 相談で確認する項目の説明

設定方法:
- Streamlit Secrets または環境変数に CONTACT_URL を設定すると「導入相談（無料）」ボタンが有効になります。
  例: CONTACT_URL="https://forms.gle/xxxxxxxx"
- CONTACT_URL がない場合、CONTACT_EMAIL を設定すると mailto リンクになります。
  例: CONTACT_EMAIL="example@example.com"

未設定の場合:
- 導入相談ボタンは「リンク未設定」として無効表示されます。
- メール文面作成ボタンは表示されます。

## 2026-04-26 導入相談導線の強化

以下の3点を追加しました。

1. 画面右上に、スクロールしても消えない固定の「📩 導入相談」ボタンを表示
2. ヒーロー内の「導入相談はこちら」ボタンを大きく、営業デモ向けに強調
3. 回答後・該当なし時に、自然な導入相談CTAを表示

CONTACT_URL または CONTACT_EMAIL が未設定の場合、固定ボタンは無効表示になります。
