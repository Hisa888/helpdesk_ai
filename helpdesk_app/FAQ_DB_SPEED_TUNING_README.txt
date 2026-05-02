FAQ DB高速化チューニング版

主な修正点:
1. FAQ保存後のDB全件再読込を廃止
   - 反映対象DataFrameはすでに最終形のため、保存直後にSQLiteから全件SELECTし直さない。

2. st.cache_resource.clear() / st.cache_data.clear() を廃止
   - FAQ更新時にアプリ全体のキャッシュを消していたため、次回検索やモデル初期化が重くなっていた。
   - FAQインデックス系キャッシュだけを狙ってクリアする方式に変更。

3. SQLite保存方式を高速な全置換に変更
   - 既存データを残す/追加/更新/削除の判定は apply_faq_upload_operations 側で実施済み。
   - DB内部保存は DELETE一括 + executemany一括INSERT を標準にして高速化。
   - 差分UPSERT方式に戻したい場合は HELP_DESK_FAQ_DB_SYNC_MODE=upsert を設定。

4. GitHub永続化を非同期化
   - FAQ反映時にGitHub APIの完了を待たず、画面の体感速度を優先。
   - ローカル保存とDB保存は先に完了する。

5. CSV同期を環境変数でOFF可能
   - 通常はExcelダウンロード/互換性のため faq.csv も同期。
   - 極端に件数が多くCSV同期が重い場合は HELP_DESK_FAQ_SYNC_CSV=0 を設定するとDBのみ保存。

確認ポイント:
- FAQをアップロードして、反映時間が短くなっていること
- 反映後の件数が正しいこと
- 既存FAQが消えないこと
- 次の問い合わせ検索が以前より重くならないこと
