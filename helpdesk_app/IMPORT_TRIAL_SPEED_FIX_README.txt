# ImportError / 期限表示 / 検索速度 修正

## 修正内容
- trial_license.py に get_tenant_license を正しく含め、ImportError を解消
- 古い __pycache__ をZIPから除外
- 無料トライアル期限表示を左サイドバーに固定
- 既存DBの expire_date が空の場合、DEFAULT_TRIAL_EXPIRE_DATE で自動補完
- LLM再ランキングの初期値をOFFにして検索速度低下を抑制
- ログイン画面の不要なTENANT_USERS説明メッセージを削除

## 注意
既存の runtime_data/tenant_licenses.db に古い空データが残っていても、起動時に期限日が補完されます。
