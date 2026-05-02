FAQ類似検索 numpy高速化パッチ

目的:
- FAQ数が数百〜数千件でも、検索時の体感速度を上げる。
- TF-IDF計算後の類似度計算・上位候補抽出・補正処理を軽量化する。

主な修正:
1. cosine_similarity を毎回使わず、TF-IDFの疎行列内積で類似度を算出
   - TF-IDFは標準でL2正規化されるため、内積でcosine相当のスコアを取得できます。
   - query_vector @ matrix.T により高速化。

2. 全件ソートを廃止
   - sims.argsort()[::-1] で全件ソートせず、np.argpartition で上位候補だけ抽出。
   - FAQ件数が増えた時に効果が出ます。

3. DataFrame.apply の全件処理を削減
   - contains/token/concept/domain_penalty の補正を全FAQに対して実行せず、TF-IDF上位候補＋完全一致候補だけに限定。
   - 検索精度に必要な補正は残しつつ、無駄なPythonループを削減。

4. 完全一致候補は高速lookup mapから追加
   - TF-IDF候補に入らない完全一致FAQも落とさないよう維持。

修正ファイル:
- helpdesk_app/modules/search_runtime.py

確認ポイント:
- 1回目の検索速度
- 2回目以降の検索速度
- 「パスワード忘れた」など既存の高速回答
- 「アカウントがロックされた」など候補表示・直接回答
- FAQ件数が多いCSV/DBでの検索速度
