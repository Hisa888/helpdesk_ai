# AWS前の整理メモ（Step12）

## 今回の目的
AWSへアップする前に、**動作に不要なファイル**と**保守上まぎらわしいファイル**を整理し、
本番配置物をできるだけ分かりやすくする。

## 今回削除したもの
- `__pycache__/` 一式
- `legacy_runtime - 修正前.py` 相当のバックアップファイル

理由:
- 本番実行に不要
- 誤って古いファイルを参照する事故を防ぐため
- ZIPサイズ縮小

## 本番に残すもの
- `app.py`
- `refactored_helpdesk_app/entrypoint.py`
- `refactored_helpdesk_app/legacy_runtime.py`
- `refactored_helpdesk_app/runtime_main.py`
- `refactored_helpdesk_app/modules/*.py`
- `refactored_helpdesk_app/admin_menu_complete.py`
- `faq.csv` や `logs/` など実データ
- `requirements.txt`
- `.streamlit/secrets.toml` または環境変数

## 本番に含めないほうがよいもの
- `__pycache__/`
- `*.pyc`
- `legacy_runtime - 修正前.py` のようなバックアップファイル
- 途中作業用ZIP
- ローカル検証用メモ
- 個人用スクリーンショット

## AWS配置前チェック
1. `app.py` から起動できること
2. `entrypoint.py` が `legacy_runtime.run_app` を呼ぶこと
3. `legacy_runtime.py` が `runtime_main.run_app` を呼ぶこと
4. `modules/` に必要ファイルが揃っていること
5. 機密情報をソース直書きしていないこと
6. `logs/` や `runtime_data/` の書き込み権限があること
7. 日本語CSVでBOM付き保存が維持されていること

## 次の整理候補
- `runtime_main.py` に残る旧補助関数の精査
- `modules/core_io.py` / `modules/ui_helpers.py` / `modules/search_engine.py` / `modules/pdf_reports.py` の役割再整理
- 未使用importの削減
- `services/` ディレクトリが別途あるなら、依存先の棚卸し
