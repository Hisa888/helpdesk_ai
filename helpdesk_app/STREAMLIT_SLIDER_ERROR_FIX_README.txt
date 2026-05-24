StreamlitAPIException 修正

原因:
検索精度設定の「候補表示しきい値」slider で、
自動回答しきい値を 0.10 にした場合、
min_value=0.05 / max_value=0.05 となり、
StreamlitAPIException が発生していました。

対応:
候補表示しきい値 slider を安全化し、
min_value と max_value が同値にならないよう修正しました。

対象:
helpdesk_app/modules/search_settings_panel.py
