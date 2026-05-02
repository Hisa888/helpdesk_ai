FAQ差分取込の修正内容

原因:
管理画面の実行コンテキストに read_faq_operation_uploaded_file / apply_faq_upload_operations が渡されていなかったため、
「操作」列が存在するExcelでも通常取込扱いになり、後続で NoneType object is not callable が発生していました。

修正:
- app_surface_runner.py の admin_surface_ctx に差分取込関数を追加
- faq_admin_panel.py 側で callable チェックを追加し、関数未設定時に None を呼ばないよう防御

期待動作:
操作列があるExcelでは、+ は追加、空白は更新、- は削除として差分取込プレビューに進みます。
+追加時のFAQ_IDはアップロード値を使わず、自動採番します。
