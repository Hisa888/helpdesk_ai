FAQ初回レスポンス高速化パッチ

修正内容:
- 起動時にFAQ読み込み、正規化、Word/Char TF-IDFを事前生成
- 高速直答用lookup mapも事前生成
- FAQ更新トークンが変わった時だけ再ウォームアップ
- SentenceTransformerは起動を重くしやすいため対象外

確認方法:
streamlit run app.py 後、最初の質問「パスワード忘れた」「VPNにつながらない」の初回応答速度を確認してください。
