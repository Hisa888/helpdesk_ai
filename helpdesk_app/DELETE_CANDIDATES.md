# 削除候補メモ（Step12時点）

以下は**即削除確定ではなく、確認後に整理するとよい候補**です。

## すでに削除済み
- `__pycache__/`
- `legacy_runtime - 修正前.py` 相当ファイル

## 内容確認後に整理したい候補
- `modules/ui_helpers.py`
  - サイズが小さく、現状の分割後に役割が薄い可能性あり
- `modules/core_io.py`
  - 旧runtime由来の補助関数が残っている可能性あり
- `modules/search_engine.py`
  - `modules/search_runtime.py` へ移行済み部分と役割重複の可能性あり
- `modules/pdf_reports.py`
  - `modules/pdf_runtime.py` と重複の可能性あり
- `admin_menu_complete.py`
  - 現在の `main_view_runtime.py` / `admin_panels.py` 導線と重複確認が必要

## 削除前に必ず確認すること
- `import` されていないか
- `runtime_main.py` から参照されていないか
- `entrypoint.py` / `legacy_runtime.py` の呼び出し経路に入っていないか
- Streamlitの管理画面で実際に使われていないか

## 安全な削除手順
1. 候補ファイルを1つだけ退避
2. ローカル起動
3. 一般画面 / 管理画面 / PDF / FAQ更新 / ログ出力を確認
4. 問題なければGitへ反映

