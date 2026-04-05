# legacy_runtime.py 分割マップ

安全優先の第一段階として、エントリポイント互換を維持したまま `legacy_runtime.py` を薄いラッパーに変更し、
実処理本体を `runtime_main.py` に退避しました。

## 現在の呼び出し経路
- `app.py`
- `helpdesk_app.entrypoint.run_app`
- `helpdesk_app.legacy_runtime.run_app`
- `helpdesk_app.runtime_main.run_app`

## 既存の機能別モジュール
- `modules/core_io.py` : CSV/Excel/ZIP などI/O系
- `modules/settings_and_persistence.py` : UI設定、LLM設定、永続化
- `modules/search_engine.py` : 検索、RAG、sentence-transformers
- `modules/pdf_reports.py` : PDF生成
- `modules/ui_helpers.py` : 一致度表示などUI補助
- `modules/faq_admin_panel.py` : FAQ管理パネル
- `modules/search_settings_panel.py` : 検索設定パネル
- `modules/ui_theme_panel.py` : UI配色設定パネル
- `modules/ui_layout_panel.py` : UIレイアウト設定パネル
- `modules/pdf_panels.py` : PDF出力パネル
- `modules/admin_panels.py` : 上記UIパネルの集約エクスポート

## 次段階の安全な分離候補
1. `runtime_main.py` から管理者パネル描画部分を `modules/admin_panels.py` 経由に置換
2. PDF生成群を `modules/pdf_reports.py` に完全移管
3. 検索群を `modules/search_engine.py` に完全移管
4. 設定/永続化群を `modules/settings_and_persistence.py` に完全移管


## Step7
- 設定ロード保存系と GitHub永続化系を `modules/settings_and_persistence.py` に集約
- `runtime_main.py` では `create_runtime_context(...)` を呼ぶだけに整理
- UI設定 / LLM設定 / 検索設定 / 永続化ヘルパーの境界を明確化


## Step8
- FAQインデックス生成とキャッシュ処理を `modules/faq_index_runtime.py` へ分離
- `runtime_main.py` 側は FAQインデックスAPI を受け取って利用する形へ整理
- `_build_fast_lookup_maps` も同モジュールへ移動


## Step9
- 検索エンジン本体を `modules/search_runtime.py` に外出し
- `runtime_main.py` は検索コンテキスト生成と関数束縛に整理
- FAQ検索 / 超高速FAQ直答 / LLMプロンプト生成の境界を分離


## Step10
- PDF生成系を `modules/pdf_runtime.py` へ分離
- `runtime_main.py` から ReportLab 依存とPDF生成関数群を切り離し
- 操作説明書 / 提案資料 / 効果レポートPDF をモジュール呼び出し化


## Step11
- 表示フローとサイドバー描画を `modules/main_view_runtime.py` へ分離
- `runtime_main.py` から営業デモKPI表示、一般向けサイドバー、管理者ログイン導線を切り離し
- 画面表示の責務と業務ロジックの責務をさらに分離


## Step12
- `__pycache__` を削除
- 旧バックアップの `legacy_runtime - 修正前.py` 相当ファイルを削除
- AWS前の整理資料として `AWS_DEPLOY_CLEANUP.md` / `DELETE_CANDIDATES.md` / `CLEAN_PACKAGE.ps1` を追加
- 本番に不要な作業ファイルを混ぜにくい状態へ調整
